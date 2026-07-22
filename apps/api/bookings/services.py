from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, models, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingPassenger, SeatAssignment
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey, OutboxEvent
from fleet.models import SeatAdjacency
from identity.models import User
from identity.normalization import normalize_email, normalize_phone
from policies.models import PolicyAcceptance
from policies.services import record_policy_acceptances
from trips.models import SeatHold, Trip, TripSeat
from trips.pricing import booking_quote, payment_methods, policy_version_ids
from trips.public_services import assert_public_bookable, hold_belongs_to_token, hold_hash, parse_hold_token


def _request_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _client_key(request: HttpRequest, trip_id: str) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")
    return f"public-hold:{trip_id}:{remote}"


def _enforce_rate_limit(request: HttpRequest, trip_id: str) -> None:
    key = _client_key(request, trip_id)
    count = cache.get(key, 0)
    limit = int(settings.PUBLIC_HOLD_RATE_LIMIT)
    if int(count) >= limit:
        raise DomainAPIException("RATE_LIMITED")
    if count:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=int(settings.PUBLIC_HOLD_RATE_WINDOW_SECONDS))
    else:
        cache.set(key, 1, timeout=int(settings.PUBLIC_HOLD_RATE_WINDOW_SECONDS))


def _new_hold_token(batch_id: uuid.UUID) -> str:
    return f"{batch_id}.{secrets.token_urlsafe(32)}"


def expire_due_holds(
    *,
    now: datetime | None = None,
    trip_id: uuid.UUID | None = None,
    seat_ids: list[uuid.UUID] | None = None,
) -> int:
    current = now or timezone.now()
    queryset = SeatHold.objects.filter(
        status=SeatHold.Status.ACTIVE,
        expires_at__lte=current,
    )
    if trip_id is not None:
        queryset = queryset.filter(trip_id=trip_id)
    if seat_ids is not None:
        queryset = queryset.filter(trip_seat_id__in=seat_ids)
    return queryset.update(status=SeatHold.Status.EXPIRED, released_at=current)


@transaction.atomic
def create_public_seat_hold(
    *,
    trip_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    request: HttpRequest,
) -> dict[str, Any]:
    trip = Trip.objects.select_for_update().select_related("office", "seat_layout").filter(public_id=trip_id).first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    assert_public_bookable(trip)

    fingerprint = _request_fingerprint(payload)
    idempotency = (
        IdempotencyKey.objects.select_for_update()
        .filter(scope_type="public_seat_hold", scope_id=trip.id, key=idempotency_key)
        .first()
    )
    if idempotency is not None:
        if idempotency.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        if idempotency.response_body is not None:
            return dict(idempotency.response_body)
    else:
        # A replay with the same key returns above and must not consume a new
        # rate-limit unit. Only genuinely new hold attempts are counted.
        _enforce_rate_limit(request, trip_id)
        idempotency = IdempotencyKey.objects.create(
            scope_type="public_seat_hold",
            scope_id=trip.id,
            key=idempotency_key,
            request_hash=fingerprint,
            locked_until=timezone.now() + timedelta(seconds=30),
            expires_at=timezone.now() + timedelta(hours=1),
        )

    quote_version = payload.get("quote_version")
    if quote_version is not None and int(quote_version) != trip.version:
        raise DomainAPIException("PRICE_CHANGED", details={"quote_version": trip.version})

    seat_ids = list(payload["seat_ids"])
    passenger_count = len(payload["passengers"])
    now = timezone.now()
    seats = list(
        TripSeat.objects.select_for_update()
        .filter(trip=trip, id__in=seat_ids, is_current=True)
        .select_related("layout_seat")
        .order_by("id")
    )
    if len(seats) != len(seat_ids):
        raise DomainAPIException("SEAT_LAYOUT_MISMATCH")
    expire_due_holds(now=now, trip_id=trip.id, seat_ids=[seat.id for seat in seats])
    if any(not seat.sellable for seat in seats):
        raise DomainAPIException("SEAT_NOT_AVAILABLE")
    assigned = set(
        trip.seat_assignments.filter(status="active", trip_seat_id__in=seat_ids).values_list("trip_seat_id", flat=True)
    )
    active_holds = set(
        SeatHold.objects.filter(
            trip=trip,
            trip_seat_id__in=seat_ids,
            status=SeatHold.Status.ACTIVE,
            expires_at__gt=now,
        ).values_list("trip_seat_id", flat=True)
    )
    if assigned or active_holds:
        raise DomainAPIException("SEAT_NOT_AVAILABLE", details={"seat_ids": [str(v) for v in assigned | active_holds]})

    batch_id = uuid.uuid4()
    token = _new_hold_token(batch_id)
    expires_at = now + timedelta(seconds=int(settings.SEAT_HOLD_TTL_SECONDS))
    quote = booking_quote(trip, passenger_count=passenger_count)
    stored_quote = json.loads(json.dumps(quote, default=str))
    rows = [
        SeatHold(
            trip=trip,
            trip_seat=seat,
            hold_token_hash=hold_hash(token, seat.id),
            owner_booking_draft_id=batch_id,
            quote_version=trip.version,
            quote_snapshot=stored_quote,
            status=SeatHold.Status.ACTIVE,
            expires_at=expires_at,
        )
        for seat in seats
    ]
    try:
        with transaction.atomic():
            SeatHold.objects.bulk_create(rows)
    except IntegrityError as exc:
        raise DomainAPIException("SEAT_NOT_AVAILABLE") from exc

    response = {
        "hold_token": token,
        "expires_at": expires_at,
        "quote": quote,
    }
    stored_response = json.loads(json.dumps(response, default=str))
    idempotency.response_status = 200
    idempotency.response_body = stored_response
    idempotency.locked_until = None
    idempotency.save(update_fields=["response_status", "response_body", "locked_until"])
    OutboxEvent.objects.create(
        aggregate_type="seat_hold",
        aggregate_id=batch_id,
        event_type="booking.seat_hold.created",
        payload={
            "trip_id": trip.public_id,
            "seat_ids": [str(seat.id) for seat in seats],
            "expires_at": expires_at.isoformat(),
        },
    )
    return response


@transaction.atomic
def release_public_seat_hold(*, hold_token: str) -> bool:
    parsed = parse_hold_token(hold_token)
    if parsed is None:
        raise DomainAPIException("SEAT_HOLD_NOT_OWNED")
    batch_id, _ = parsed
    holds = list(SeatHold.objects.select_for_update().filter(owner_booking_draft_id=batch_id).order_by("id"))
    if not holds or any(not hold_belongs_to_token(hold, hold_token, batch_id) for hold in holds):
        raise DomainAPIException("SEAT_HOLD_NOT_OWNED")
    now = timezone.now()
    changed = False
    for hold in holds:
        if hold.status == SeatHold.Status.ACTIVE and hold.expires_at > now:
            hold.status = SeatHold.Status.RELEASED
            hold.released_at = now
            hold.save(update_fields=["status", "released_at"])
            changed = True
        elif hold.status == SeatHold.Status.ACTIVE:
            hold.status = SeatHold.Status.EXPIRED
            hold.released_at = now
            hold.save(update_fields=["status", "released_at"])
    return changed


def _booking_client_key(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")
    return f"public-booking:{remote}"


def _enforce_booking_rate_limit(request: HttpRequest) -> None:
    key = _booking_client_key(request)
    count = int(cache.get(key, 0) or 0)
    limit = int(settings.PUBLIC_BOOKING_RATE_LIMIT)
    if count >= limit:
        raise DomainAPIException("RATE_LIMITED")
    if count:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=int(settings.PUBLIC_BOOKING_RATE_WINDOW_SECONDS))
    else:
        cache.set(key, 1, timeout=int(settings.PUBLIC_BOOKING_RATE_WINDOW_SECONDS))


def _manage_token(booking: Booking) -> str:
    key = str(settings.BOOKING_MANAGE_TOKEN_KEY).encode()
    payload = f"v1:{booking.id}:{booking.public_id}".encode()
    digest = hmac.new(key, payload, hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return f"mb1_{encoded}"


def _manage_token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def manage_token_matches(booking: Booking, token: str) -> bool:
    return hmac.compare_digest(bytes(booking.manage_token_hash), _manage_token_hash(token))


def _decimal_amount(quote: dict[str, Any], field: str) -> Decimal:
    value = quote.get(field, {})
    if not isinstance(value, dict) or "amount" not in value:
        raise DomainAPIException("PRICE_CHANGED")
    return Decimal(str(value["amount"]))


def _validate_policy_acceptance(trip: Trip, accepted_ids: list[str]) -> list[str]:
    required = policy_version_ids(trip)
    accepted = sorted({str(item) for item in accepted_ids})
    if accepted != required:
        raise DomainAPIException(
            "POLICY_ACCEPTANCE_REQUIRED",
            details={"required_policy_version_ids": required},
        )
    return required


def _selected_gender_map(passengers: list[dict[str, Any]]) -> dict[uuid.UUID, str]:
    mapping: dict[uuid.UUID, str] = {}
    for passenger in passengers:
        seat_id = passenger.get("seat_id")
        if seat_id is None:
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": "passengers.seat_id", "reason": "required"}],
            )
        mapping[uuid.UUID(str(seat_id))] = str(passenger["gender"])
    return mapping


def _assert_gender_adjacency(
    *,
    trip: Trip,
    selected_seats: list[TripSeat],
    passengers: list[dict[str, Any]],
    ignore_booking_id: uuid.UUID | None = None,
) -> None:
    selected_gender = _selected_gender_map(passengers)
    selected_ids = set(selected_gender)
    layout_to_trip = {seat.layout_seat_id: seat.id for seat in trip.seats.filter(is_current=True)}
    selected_layout_ids = {seat.layout_seat_id for seat in selected_seats}
    adjacency_rows = SeatAdjacency.objects.filter(
        layout=trip.seat_layout,
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
    ).filter(models.Q(seat_a_id__in=selected_layout_ids) | models.Q(seat_b_id__in=selected_layout_ids))
    adjacent_trip_ids: set[uuid.UUID] = set()
    pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
    for adjacency in adjacency_rows:
        first = layout_to_trip.get(adjacency.seat_a_id)
        second = layout_to_trip.get(adjacency.seat_b_id)
        if first is None or second is None:
            continue
        pairs.append((first, second))
        adjacent_trip_ids.update({first, second})

    existing_queryset = SeatAssignment.objects.select_related("passenger").filter(
        trip=trip,
        trip_seat_id__in=adjacent_trip_ids,
        status=SeatAssignment.Status.ACTIVE,
    )
    if ignore_booking_id is not None:
        existing_queryset = existing_queryset.exclude(booking_id=ignore_booking_id)
    existing = {assignment.trip_seat_id: assignment.passenger.gender for assignment in existing_queryset}
    for first, second in pairs:
        if first in selected_ids and second in selected_ids:
            # Different genders are explicitly allowed inside the same booking.
            continue
        selected_id = first if first in selected_ids else second if second in selected_ids else None
        other_id = second if selected_id == first else first
        if selected_id is None or other_id not in existing:
            continue
        if selected_gender[selected_id] != existing[other_id]:
            # Do not disclose the adjacent passenger's gender or booking.
            raise DomainAPIException("SEAT_GENDER_CONFLICT")


def _grouping_snapshot(
    *,
    selected_seats: list[TripSeat],
    passengers: list[dict[str, Any]],
    trip: Trip,
) -> dict[str, Any]:
    sequence_by_seat = {
        uuid.UUID(str(passenger["seat_id"])): index for index, passenger in enumerate(passengers, start=1)
    }
    type_by_sequence = {
        index: str(passenger.get("passenger_type", BookingPassenger.PassengerType.ADULT))
        for index, passenger in enumerate(passengers, start=1)
    }
    layout_to_trip = {seat.layout_seat_id: seat.id for seat in selected_seats}
    same_unit_pairs: set[tuple[int, int]] = set()
    for adjacency in SeatAdjacency.objects.filter(
        layout=trip.seat_layout,
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
        seat_a_id__in=layout_to_trip,
        seat_b_id__in=layout_to_trip,
    ):
        first = sequence_by_seat[layout_to_trip[adjacency.seat_a_id]]
        second = sequence_by_seat[layout_to_trip[adjacency.seat_b_id]]
        lower, upper = sorted((first, second))
        same_unit_pairs.add((lower, upper))

    protected_groups: list[dict[str, Any]] = []
    review_sequences: list[int] = []
    adults = {sequence for sequence, kind in type_by_sequence.items() if kind == BookingPassenger.PassengerType.ADULT}
    for sequence, kind in type_by_sequence.items():
        if kind not in {BookingPassenger.PassengerType.CHILD, BookingPassenger.PassengerType.INFANT}:
            continue
        guardian = next(
            (
                other
                for pair in same_unit_pairs
                if sequence in pair
                for other in pair
                if other != sequence and other in adults
            ),
            None,
        )
        if guardian is None:
            review_sequences.append(sequence)
        else:
            protected_groups.append({"dependent_sequence": sequence, "guardian_sequence": guardian})
    return {
        "same_unit_pairs": [list(pair) for pair in sorted(same_unit_pairs)],
        "protected_groups": protected_groups,
        "requires_reassignment_review_for_sequences": review_sequences,
    }


def _booking_queryset() -> models.QuerySet[Booking]:
    return Booking.objects.select_related(
        "trip__route__origin_location",
        "trip__route__destination_location",
        "trip__office",
    ).prefetch_related(
        "passengers__tickets__seat_assignment__trip_seat",
        "seat_assignments__trip_seat",
        "trip_change_responses__change",
    )


def _serialize_booking(booking: Booking, *, manage_token: str | None = None) -> dict[str, Any]:
    from tickets.models import Ticket
    from tickets.services import serialize_ticket

    active_assignments = {
        item.passenger_id: item
        for item in booking.seat_assignments.all()
        if item.status == SeatAssignment.Status.ACTIVE
    }
    latest_assignments: dict[uuid.UUID, SeatAssignment] = {}
    for assignment in sorted(booking.seat_assignments.all(), key=lambda item: item.assigned_at):
        latest_assignments[assignment.passenger_id] = assignment
    active_tickets = {
        ticket.passenger_id: ticket
        for passenger in booking.passengers.all()
        for ticket in passenger.tickets.all()
        if ticket.status == Ticket.Status.ACTIVE
    }
    trip = booking.trip
    passengers: list[dict[str, Any]] = []
    for passenger in booking.passengers.all():
        current_assignment: SeatAssignment | None = active_assignments.get(passenger.id) or latest_assignments.get(
            passenger.id
        )
        ticket = active_tickets.get(passenger.id)
        passengers.append(
            {
                "id": str(passenger.id),
                "full_name": passenger.full_name,
                "gender": passenger.gender,
                "passenger_type": passenger.passenger_type,
                "date_of_birth": passenger.date_of_birth,
                "nationality_code": passenger.nationality_code,
                "boarding_status": passenger.boarding_status,
                "status": passenger.status,
                "seat_id": (str(current_assignment.trip_seat_id) if current_assignment is not None else None),
                "seat_code": (current_assignment.trip_seat.seat_code if current_assignment is not None else None),
                "ticket": serialize_ticket(ticket) if ticket is not None else None,
            }
        )
    trip_changes = [
        {
            "change_id": str(response.change_id),
            "change_type": response.change.change_type,
            "classification": response.change.classification,
            "status": response.status,
            "response_deadline_at": response.change.response_deadline_at,
            "previous_snapshot": response.change.previous_snapshot,
            "new_snapshot": response.change.new_snapshot,
        }
        for response in booking.trip_change_responses.all()
    ]
    payload: dict[str, Any] = {
        "id": booking.public_id,
        "pnr": booking.pnr,
        "status": booking.status,
        "payment_status": booking.payment_status,
        "trip": {
            "id": trip.public_id,
            "departure_at": trip.scheduled_departure_at,
            "arrival_at": trip.scheduled_arrival_at,
            "origin": {
                "id": trip.route.origin_location.public_id,
                "name": trip.route.origin_location.name_ar,
            },
            "destination": {
                "id": trip.route.destination_location.public_id,
                "name": trip.route.destination_location.name_ar,
            },
            "office": {"id": trip.office.public_id, "name": trip.office.trade_name},
        },
        "contact": {
            "name": booking.contact_name,
            "phone": booking.contact_phone,
            "email": booking.contact_email,
        },
        "passengers": passengers,
        "pricing": {
            "subtotal": {"amount": str(booking.subtotal_amount), "currency": booking.currency},
            "discount": {"amount": str(booking.discount_amount), "currency": booking.currency},
            "fees": {"amount": str(booking.fee_amount), "currency": booking.currency},
            "total": {"amount": str(booking.total_amount), "currency": booking.currency},
            "payment_deadline_at": booking.payment_deadline_at,
            "policy_version_ids": booking.terms_version_ids,
            "quote_version": booking.pricing_snapshot.get("quote_version", trip.version),
        },
        "payment_deadline_at": booking.payment_deadline_at,
        "payment_methods": [str(value) for value in trip.pricing_snapshot.get("payment_methods", [])],
        "outstanding_amount": str(max(Decimal("0.00"), booking.total_amount - booking.paid_amount)),
        "created_at": booking.created_at,
        "trip_changes": trip_changes,
        "manage_actions": [
            "view",
            "download",
            "print",
            *(
                ["pay"]
                if booking.payment_status not in {Booking.PaymentStatus.PAID, Booking.PaymentStatus.REFUNDED}
                else []
            ),
            *(["respond_trip_change"] if any(change["status"] == "pending" for change in trip_changes) else []),
            *(
                ["cancel"]
                if any(passenger.status == BookingPassenger.Status.ACTIVE for passenger in booking.passengers.all())
                else []
            ),
        ],
    }
    if manage_token is not None:
        payload["manage_token"] = manage_token
    return payload


def _lookup_client_key(request: HttpRequest) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    remote = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "unknown")
    return f"public-booking-lookup:{remote}"


def _enforce_lookup_rate_limit(request: HttpRequest) -> None:
    key = _lookup_client_key(request)
    count = int(cache.get(key, 0) or 0)
    limit = int(settings.PUBLIC_BOOKING_LOOKUP_RATE_LIMIT)
    if count >= limit:
        raise DomainAPIException("RATE_LIMITED")
    if count:
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=int(settings.PUBLIC_BOOKING_LOOKUP_RATE_WINDOW_SECONDS))
    else:
        cache.set(key, 1, timeout=int(settings.PUBLIC_BOOKING_LOOKUP_RATE_WINDOW_SECONDS))


def _contact_matches(booking: Booking, verifier: str) -> bool:
    candidate = verifier.strip()
    try:
        normalized_phone = normalize_phone(candidate)
    except ValueError:
        normalized_phone = None
    normalized_email = normalize_email(candidate)
    return bool(
        (normalized_phone and hmac.compare_digest(booking.contact_phone, normalized_phone))
        or (
            normalized_email
            and booking.contact_email
            and hmac.compare_digest(booking.contact_email.lower(), normalized_email.lower())
        )
    )


def get_public_booking(*, pnr: str, manage_token: str) -> dict[str, Any]:
    booking = _booking_queryset().filter(pnr=pnr.strip().upper()).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return _serialize_booking(booking)


def lookup_public_booking(
    *,
    pnr: str,
    contact_verifier: str,
    request: HttpRequest,
) -> dict[str, Any]:
    _enforce_lookup_rate_limit(request)
    booking = _booking_queryset().filter(pnr=pnr.strip().upper()).first()
    if booking is None or not _contact_matches(booking, contact_verifier):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return _serialize_booking(booking, manage_token=_manage_token(booking))


def list_customer_bookings(*, user: User, status_filter: str | None = None) -> list[dict[str, Any]]:
    queryset = _booking_queryset().filter(customer_user=user).order_by("-created_at")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return [_serialize_booking(booking) for booking in queryset]


@transaction.atomic
def link_guest_booking_to_customer(
    *,
    user: User,
    pnr: str,
    manage_token: str,
) -> dict[str, Any]:
    booking = _booking_queryset().select_for_update().filter(pnr=pnr.strip().upper()).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    verified_contacts = {
        value.lower()
        for value in [
            user.email if user.email_verified_at else None,
            user.phone_e164 if user.phone_verified_at else None,
        ]
        if value
    }
    booking_contacts = {value.lower() for value in [booking.contact_email, booking.contact_phone] if value}
    if not verified_contacts.intersection(booking_contacts):
        raise DomainAPIException("PERMISSION_DENIED")
    if booking.customer_user_id not in {None, user.id}:
        raise DomainAPIException("CONFLICT")
    booking.customer_user = user
    booking.save(update_fields=["customer_user", "updated_at"])
    return _serialize_booking(booking)


@transaction.atomic
def create_public_booking(
    *,
    payload: dict[str, Any],
    idempotency_key: str,
    request: HttpRequest,
) -> dict[str, Any]:
    trip = (
        Trip.objects.select_for_update()
        .select_related(
            "office",
            "branch",
            "route__origin_location",
            "route__destination_location",
            "seat_layout",
        )
        .filter(public_id=str(payload["trip_id"]))
        .first()
    )
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")

    fingerprint = _request_fingerprint(payload)
    idempotency = (
        IdempotencyKey.objects.select_for_update()
        .filter(scope_type="public_booking", scope_id=trip.id, key=idempotency_key)
        .first()
    )
    if idempotency is not None:
        if idempotency.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        if idempotency.response_body is not None:
            replay = dict(idempotency.response_body)
            booking = Booking.objects.filter(public_id=str(replay.get("id", ""))).first()
            if booking is None:
                raise DomainAPIException("CONFLICT", details={"reason": "idempotency_result_missing"})
            replay["manage_token"] = _manage_token(booking)
            return replay
    else:
        _enforce_booking_rate_limit(request)
        idempotency = IdempotencyKey.objects.create(
            scope_type="public_booking",
            scope_id=trip.id,
            key=idempotency_key,
            request_hash=fingerprint,
            locked_until=timezone.now() + timedelta(seconds=45),
            expires_at=timezone.now() + timedelta(hours=24),
        )

    assert_public_bookable(trip)
    accepted_ids = _validate_policy_acceptance(trip, [str(item) for item in payload["accepted_policy_version_ids"]])
    method = str(payload["payment_method"])
    if method not in payment_methods(trip):
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "payment_method", "reason": "not_available_for_trip"}],
        )

    parsed = parse_hold_token(str(payload["hold_token"]))
    if parsed is None:
        raise DomainAPIException("SEAT_HOLD_NOT_OWNED")
    batch_id, _ = parsed
    holds = list(
        SeatHold.objects.select_for_update()
        .select_related("trip_seat__layout_seat")
        .filter(owner_booking_draft_id=batch_id)
        .order_by("trip_seat_id")
    )
    if not holds or any(
        hold.trip_id != trip.id or not hold_belongs_to_token(hold, str(payload["hold_token"]), batch_id)
        for hold in holds
    ):
        raise DomainAPIException("SEAT_HOLD_NOT_OWNED")
    now = timezone.now()
    if any(hold.status != SeatHold.Status.ACTIVE or hold.expires_at <= now for hold in holds):
        for hold in holds:
            if hold.status == SeatHold.Status.ACTIVE and hold.expires_at <= now:
                hold.status = SeatHold.Status.EXPIRED
                hold.released_at = now
                hold.save(update_fields=["status", "released_at"])
        raise DomainAPIException("SEAT_HOLD_EXPIRED")
    if any(hold.quote_version != trip.version for hold in holds):
        raise DomainAPIException("PRICE_CHANGED", details={"quote_version": trip.version})

    passengers = list(payload["passengers"])
    seat_ids = [uuid.UUID(str(passenger["seat_id"])) for passenger in passengers]
    held_ids = [hold.trip_seat_id for hold in holds]
    if len(passengers) != len(holds) or set(seat_ids) != set(held_ids) or len(seat_ids) != len(set(seat_ids)):
        raise DomainAPIException("SEAT_LAYOUT_MISMATCH")

    selected_seats = list(
        TripSeat.objects.select_for_update()
        .select_related("layout_seat")
        .filter(trip=trip, id__in=seat_ids, is_current=True)
        .order_by("id")
    )
    if len(selected_seats) != len(seat_ids) or any(not seat.sellable for seat in selected_seats):
        raise DomainAPIException("SEAT_NOT_AVAILABLE")
    if SeatAssignment.objects.filter(
        trip=trip,
        trip_seat_id__in=seat_ids,
        status=SeatAssignment.Status.ACTIVE,
    ).exists():
        raise DomainAPIException("SEAT_NOT_AVAILABLE")

    _assert_gender_adjacency(trip=trip, selected_seats=selected_seats, passengers=passengers)
    grouping = _grouping_snapshot(trip=trip, selected_seats=selected_seats, passengers=passengers)
    quote = dict(holds[0].quote_snapshot)
    if any(dict(hold.quote_snapshot) != quote for hold in holds):
        raise DomainAPIException("PRICE_CHANGED")

    contact = dict(payload["contact"])
    try:
        normalized_phone = normalize_phone(str(contact["phone"]))
    except ValueError as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "contact.phone", "reason": "e164_required"}],
        ) from exc
    normalized_email = normalize_email(contact.get("email"))
    status = Booking.Status.CONFIRMED if method == "office_cash" else Booking.Status.AWAITING_PAYMENT
    deadline_raw = quote.get("payment_deadline_at")
    deadline = datetime.fromisoformat(str(deadline_raw)) if deadline_raw else None
    if deadline is not None and timezone.is_naive(deadline):
        deadline = timezone.make_aware(deadline)

    policy_snapshot = json.loads(json.dumps(trip.policy_snapshot, default=str))
    policy_snapshot["passenger_grouping"] = grouping
    pricing_snapshot = json.loads(json.dumps(trip.pricing_snapshot, default=str))
    pricing_snapshot.update(
        {
            "quote_version": holds[0].quote_version,
            "quote": quote,
            "payment_method": method,
            "client_reference": payload.get("client_reference"),
            "risk_assessment_id": str(getattr(request, "risk_assessment_id", "")) or None,
        }
    )
    commission_snapshot = {
        "profile_id": str(trip.office.commission_profile_id) if trip.office.commission_profile_id else None,
        "rules": trip.pricing_snapshot.get("commission", {}),
    }

    # Generate the record first, then derive a deterministic secret from its UUID.
    booking = Booking(
        office=trip.office,
        branch=trip.branch,
        trip=trip,
        source=Booking.Source.PUBLIC_WEB,
        status=status,
        payment_status=Booking.PaymentStatus.UNPAID,
        contact_name=str(contact["name"]).strip(),
        contact_phone=normalized_phone or str(contact["phone"]),
        contact_email=normalized_email,
        currency=trip.currency,
        subtotal_amount=_decimal_amount(quote, "subtotal"),
        discount_amount=_decimal_amount(quote, "discount"),
        fee_amount=_decimal_amount(quote, "fees"),
        total_amount=_decimal_amount(quote, "total"),
        payment_deadline_at=deadline,
        policy_snapshot=policy_snapshot,
        pricing_snapshot=pricing_snapshot,
        commission_snapshot=commission_snapshot,
        terms_version_ids=accepted_ids,
        manage_token_hash=b"",
        confirmed_at=now if status == Booking.Status.CONFIRMED else None,
    )
    manage_token = _manage_token(booking)
    booking.manage_token_hash = _manage_token_hash(manage_token)
    booking.save(force_insert=True)

    raw_request_user = getattr(request, "user", None)
    request_user: User | None = raw_request_user if isinstance(raw_request_user, User) else None
    record_policy_acceptances(
        policy_version_ids=accepted_ids,
        subject_type=PolicyAcceptance.SubjectType.BOOKING,
        subject_id=booking.id,
        accepted_by_user=request_user,
        request=request,
    )

    from finance.services import create_expected_commission

    create_expected_commission(booking)

    passengers_by_seat: dict[uuid.UUID, BookingPassenger] = {}
    for sequence, passenger_data in enumerate(passengers, start=1):
        seat_id = uuid.UUID(str(passenger_data["seat_id"]))
        passenger = BookingPassenger.objects.create(
            booking=booking,
            sequence_no=sequence,
            full_name=str(passenger_data["full_name"]).strip(),
            gender=str(passenger_data["gender"]),
            passenger_type=str(passenger_data.get("passenger_type", BookingPassenger.PassengerType.ADULT)),
            date_of_birth=passenger_data.get("date_of_birth"),
            nationality_code=(
                str(passenger_data["nationality_code"]).upper() if passenger_data.get("nationality_code") else None
            ),
        )
        passengers_by_seat[seat_id] = passenger

    unit_price = (_decimal_amount(quote, "subtotal") / Decimal(len(passengers))).quantize(Decimal("0.01"))
    try:
        SeatAssignment.objects.bulk_create(
            [
                SeatAssignment(
                    trip=trip,
                    booking=booking,
                    passenger=passengers_by_seat[seat.id],
                    trip_seat=seat,
                    price_amount=unit_price,
                )
                for seat in selected_seats
            ]
        )
    except IntegrityError as exc:
        raise DomainAPIException("SEAT_NOT_AVAILABLE") from exc

    SeatHold.objects.filter(id__in=[hold.id for hold in holds]).update(
        status=SeatHold.Status.CONSUMED,
        released_at=now,
    )
    OutboxEvent.objects.create(
        aggregate_type="booking",
        aggregate_id=booking.id,
        event_type="booking.created",
        payload={
            "booking_id": booking.public_id,
            "pnr": booking.pnr,
            "trip_id": trip.public_id,
            "status": booking.status,
            "payment_status": booking.payment_status,
        },
    )
    record_audit(
        action="booking.create_public",
        object_type="booking",
        actor_type="guest",
        office_id=trip.office_id,
        object_id=booking.id,
        request=request,
        after={
            "public_id": booking.public_id,
            "pnr": booking.pnr,
            "status": booking.status,
            "passenger_count": len(passengers),
        },
    )
    from tickets.services import issue_tickets_for_booking

    issue_tickets_for_booking(booking)
    response = _serialize_booking(
        _booking_queryset().get(id=booking.id),
        manage_token=manage_token,
    )
    stored_response = json.loads(json.dumps(response, default=str))
    stored_response.pop("manage_token", None)
    idempotency.response_status = 200
    idempotency.response_body = stored_response
    idempotency.locked_until = None
    idempotency.save(update_fields=["response_status", "response_body", "locked_until"])
    return response
