from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingChange, BookingPassenger, SeatAssignment
from bookings.services import (
    _assert_gender_adjacency,
    _booking_queryset,
    _serialize_booking,
    manage_token_matches,
)
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey, OutboxEvent
from finance.services import adjust_commission_after_booking_change, money
from identity.models import User
from organizations.services import OfficeContext
from payments.models import PaymentIntent, Refund
from tickets.services import reissue_ticket_for_passenger, revoke_tickets_for_passenger
from trips.models import SeatHold, TripSeat

NON_CANCELLABLE_BOARDING_STATES = {
    BookingPassenger.BoardingStatus.BOARDED,
    BookingPassenger.BoardingStatus.BOARDED_REVERSED,
}


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _quote_signing_key() -> bytes:
    return str(settings.CANCELLATION_QUOTE_SIGNING_KEY).encode()


def _sign_quote(payload: bytes) -> bytes:
    return hmac.new(_quote_signing_key(), payload, hashlib.sha256).digest()


def _encode_quote(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"cq1.{_b64encode(encoded)}.{_b64encode(_sign_quote(encoded))}"


def _decode_quote(token: str) -> dict[str, Any]:
    try:
        prefix, encoded, signature = token.split(".", 2)
        if prefix != "cq1":
            raise ValueError
        payload_bytes = _b64decode(encoded)
        if not hmac.compare_digest(_b64decode(signature), _sign_quote(payload_bytes)):
            raise ValueError
        payload = json.loads(payload_bytes.decode())
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)
        if expires_at <= timezone.now():
            raise DomainAPIException("CANCELLATION_QUOTE_EXPIRED")
        return dict(payload)
    except DomainAPIException:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DomainAPIException("CANCELLATION_QUOTE_INVALID") from exc


def _cancellation_rules(booking: Booking) -> dict[str, Any]:
    cancellation = booking.policy_snapshot.get("cancellation", {})
    if not isinstance(cancellation, dict):
        return {}
    rules = cancellation.get("rules", {})
    return dict(rules) if isinstance(rules, dict) else {}


def _refund_percent(booking: Booking, *, at: datetime) -> Decimal:
    rules = _cancellation_rules(booking)
    hours_before = Decimal(str(max(0.0, (booking.trip.scheduled_departure_at - at).total_seconds() / 3600)))
    tiers = rules.get("tiers", [])
    if isinstance(tiers, list):
        normalized: list[tuple[Decimal, Decimal]] = []
        for item in tiers:
            if not isinstance(item, dict):
                continue
            try:
                normalized.append(
                    (
                        Decimal(str(item.get("min_hours_before_departure", "0"))),
                        Decimal(str(item.get("refund_percent", "0"))),
                    )
                )
            except (ValueError, TypeError):
                continue
        for minimum, percent in sorted(normalized, reverse=True):
            if hours_before >= minimum:
                return max(Decimal("0"), min(Decimal("100"), percent))
    try:
        return max(
            Decimal("0"),
            min(Decimal("100"), Decimal(str(rules.get("refund_percent", "100")))),
        )
    except (ValueError, TypeError):
        return Decimal("100")


def _selected_passengers(booking: Booking, passenger_ids: list[str] | None) -> list[BookingPassenger]:
    queryset = BookingPassenger.objects.filter(
        booking=booking,
        status=BookingPassenger.Status.ACTIVE,
    ).order_by("sequence_no")
    if passenger_ids:
        try:
            parsed = {uuid.UUID(str(value)) for value in passenger_ids}
        except ValueError as exc:
            raise DomainAPIException("VALIDATION_ERROR") from exc
        queryset = queryset.filter(id__in=parsed)
    passengers = list(queryset)
    if not passengers:
        raise DomainAPIException("CANCELLATION_NOT_ALLOWED")
    if passenger_ids and len(passengers) != len(passenger_ids):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if len(passengers) < booking.passengers.filter(status=BookingPassenger.Status.ACTIVE).count():
        rules = _cancellation_rules(booking)
        if rules.get("allow_partial", True) is False:
            raise DomainAPIException("CANCELLATION_NOT_ALLOWED", details={"reason": "partial_not_allowed"})
    for passenger in passengers:
        if passenger.boarding_status in NON_CANCELLABLE_BOARDING_STATES:
            raise DomainAPIException("PASSENGER_ALREADY_BOARDED")
    return passengers


def _allocate_amount(total: Decimal, weights: list[Decimal], index: int) -> Decimal:
    total = money(total)
    weight_sum = sum(weights, Decimal("0.00"))
    if total == 0 or weight_sum <= 0:
        return Decimal("0.00")
    if index == len(weights) - 1:
        previous = sum((_allocate_amount(total, weights, i) for i in range(index)), Decimal("0.00"))
        return money(total - previous)
    return money(total * weights[index] / weight_sum)


def _quote_payload(booking: Booking, passengers: list[BookingPassenger]) -> dict[str, Any]:
    now = timezone.now()
    assignments = {
        assignment.passenger_id: assignment
        for assignment in SeatAssignment.objects.filter(
            booking=booking,
            passenger__in=passengers,
            status=SeatAssignment.Status.ACTIVE,
        ).select_related("trip_seat")
    }
    if len(assignments) != len(passengers):
        raise DomainAPIException("CANCELLATION_NOT_ALLOWED", details={"reason": "active_seat_missing"})
    weights = [money(assignments[passenger.id].price_amount) for passenger in passengers]
    all_weight = money(booking.subtotal_amount)
    selected_subtotal = money(sum(weights, Decimal("0.00")))
    selected_discount = (
        money(booking.discount_amount * selected_subtotal / all_weight) if all_weight > 0 else Decimal("0.00")
    )
    selected_fee = money(booking.fee_amount * selected_subtotal / all_weight) if all_weight > 0 else Decimal("0.00")
    selected_total = money(selected_subtotal - selected_discount + selected_fee)

    percent = _refund_percent(booking, at=now)
    rules = _cancellation_rules(booking)
    fixed_fee = money(rules.get("fixed_fee", "0"))
    policy_refund = money(max(Decimal("0.00"), selected_total * percent / Decimal("100") - fixed_fee))
    reserved_refunds = money(
        sum(
            Refund.objects.filter(
                booking=booking,
                status__in=[
                    Refund.Status.REQUESTED,
                    Refund.Status.UNDER_REVIEW,
                    Refund.Status.APPROVED,
                    Refund.Status.PROCESSING,
                    Refund.Status.SUCCEEDED,
                ],
            ).values_list("requested_amount", flat=True),
            Decimal("0.00"),
        )
    )
    available_paid = money(max(Decimal("0.00"), booking.paid_amount - reserved_refunds))
    paid_share = (
        money(available_paid * selected_total / booking.total_amount) if booking.total_amount > 0 else Decimal("0.00")
    )
    refund_amount = min(policy_refund, paid_share)
    retained_amount = money(selected_total - policy_refund)

    line_refund_weights = [money(weight) for weight in weights]
    lines: list[dict[str, Any]] = []
    for index, passenger in enumerate(passengers):
        assignment = assignments[passenger.id]
        line_subtotal = weights[index]
        line_discount = _allocate_amount(selected_discount, weights, index)
        line_fee = _allocate_amount(selected_fee, weights, index)
        line_total = money(line_subtotal - line_discount + line_fee)
        line_refund = _allocate_amount(refund_amount, line_refund_weights, index)
        lines.append(
            {
                "passenger_id": str(passenger.id),
                "full_name": passenger.full_name,
                "seat_id": str(assignment.trip_seat_id),
                "seat_code": assignment.trip_seat.seat_code,
                "subtotal_amount": str(line_subtotal),
                "discount_amount": str(line_discount),
                "fee_amount": str(line_fee),
                "total_amount": str(line_total),
                "refund_amount": str(line_refund),
                "retained_amount": str(money(line_total - line_refund)),
            }
        )
    expires_at = now + timedelta(seconds=int(settings.CANCELLATION_QUOTE_TTL_SECONDS))
    payload = {
        "booking_id": str(booking.id),
        "booking_version": booking.version,
        "passenger_ids": [str(passenger.id) for passenger in passengers],
        "lines": lines,
        "selected_subtotal": str(selected_subtotal),
        "selected_discount": str(selected_discount),
        "selected_fee": str(selected_fee),
        "selected_total": str(selected_total),
        "refund_amount": str(refund_amount),
        "retained_amount": str(retained_amount),
        "refund_percent": str(percent),
        "currency": booking.currency,
        "policy_version_id": str(
            booking.policy_snapshot.get("cancellation", {}).get("id", "snapshot")
            if isinstance(booking.policy_snapshot.get("cancellation", {}), dict)
            else "snapshot"
        ),
        "expires_at": expires_at.isoformat(),
    }
    payload["quote_token"] = _encode_quote(payload)
    return payload


def get_cancellation_quote(*, pnr: str, manage_token: str, passenger_ids: list[str] | None = None) -> dict[str, Any]:
    booking = (
        Booking.objects.select_related("trip")
        .prefetch_related("passengers", "seat_assignments__trip_seat")
        .filter(pnr=pnr.strip().upper())
        .first()
    )
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if booking.status not in {Booking.Status.CONFIRMED, Booking.Status.AWAITING_PAYMENT}:
        raise DomainAPIException("CANCELLATION_NOT_ALLOWED")
    if booking.trip.scheduled_departure_at <= timezone.now():
        raise DomainAPIException("CANCELLATION_NOT_ALLOWED")
    passengers = _selected_passengers(booking, passenger_ids)
    quote = _quote_payload(booking, passengers)
    return {
        "allowed": True,
        "refund_amount": {"amount": quote["refund_amount"], "currency": booking.currency},
        "retained_amount": {"amount": quote["retained_amount"], "currency": booking.currency},
        "reason": "snapshot_policy",
        "expires_at": quote["expires_at"],
        "quote_token": quote["quote_token"],
        "passengers": quote["lines"],
    }


def _payment_intent_for_refund(booking: Booking) -> PaymentIntent | None:
    return (
        PaymentIntent.objects.filter(
            booking=booking,
            status=PaymentIntent.Status.SUCCEEDED,
        )
        .order_by("-updated_at")
        .first()
    )


def _change_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _store_change(
    *,
    booking: Booking,
    passenger: BookingPassenger | None,
    change_type: str,
    reason_code: str | None,
    before: dict[str, Any],
    after: dict[str, Any],
    actor: User | None,
) -> BookingChange:
    return BookingChange.objects.create(
        booking=booking,
        passenger=passenger,
        change_type=change_type,
        reason_code=reason_code,
        before_snapshot=before,
        after_snapshot=after,
        created_by=actor,
    )


def _refresh_grouping_snapshot(booking: Booking) -> None:
    active = list(booking.passengers.filter(status=BookingPassenger.Status.ACTIVE).order_by("sequence_no"))
    assignments = {
        item.passenger_id: item
        for item in booking.seat_assignments.filter(status=SeatAssignment.Status.ACTIVE).select_related("trip_seat")
    }
    protected = []
    review = []
    for passenger in active:
        if passenger.passenger_type not in {
            BookingPassenger.PassengerType.CHILD,
            BookingPassenger.PassengerType.INFANT,
        }:
            continue
        assignment = assignments.get(passenger.id)
        if assignment is None:
            review.append(passenger.sequence_no)
            continue
        guardian = next(
            (
                candidate
                for candidate in active
                if candidate.passenger_type == BookingPassenger.PassengerType.ADULT
                and candidate.id in assignments
                and abs(
                    assignments[candidate.id].trip_seat.layout_seat.row_no - assignment.trip_seat.layout_seat.row_no
                )
                == 0
                and abs(
                    assignments[candidate.id].trip_seat.layout_seat.column_no
                    - assignment.trip_seat.layout_seat.column_no
                )
                == 1
            ),
            None,
        )
        if guardian is None:
            review.append(passenger.sequence_no)
        else:
            protected.append({"dependent_sequence": passenger.sequence_no, "guardian_sequence": guardian.sequence_no})
    snapshot = dict(booking.policy_snapshot)
    grouping = dict(snapshot.get("passenger_grouping", {}))
    grouping["protected_groups"] = protected
    grouping["requires_reassignment_review_for_sequences"] = review
    snapshot["passenger_grouping"] = grouping
    booking.policy_snapshot = snapshot


@transaction.atomic
def cancel_public_booking(
    *,
    pnr: str,
    manage_token: str,
    quote_token: str,
    reason_code: str,
    idempotency_key: str,
    request: HttpRequest,
) -> dict[str, Any]:
    decoded = _decode_quote(quote_token)
    booking_id = decoded.get("booking_id")
    if not isinstance(booking_id, str):
        raise DomainAPIException("CANCELLATION_QUOTE_INVALID")
    booking = _booking_queryset().select_for_update().filter(pnr=pnr.strip().upper(), id=booking_id).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    payload = {"quote_token": quote_token, "reason_code": reason_code}
    fingerprint = _change_fingerprint(payload)
    replay = (
        IdempotencyKey.objects.select_for_update()
        .filter(scope_type="public_booking_cancel", scope_id=booking.id, key=idempotency_key)
        .first()
    )
    if replay is not None:
        if replay.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        refreshed = _booking_queryset().get(id=booking.id)
        return _serialize_booking(refreshed, manage_token=manage_token)
    idempotency = IdempotencyKey.objects.create(
        scope_type="public_booking_cancel",
        scope_id=booking.id,
        key=idempotency_key,
        request_hash=fingerprint,
        locked_until=timezone.now() + timedelta(seconds=30),
        expires_at=timezone.now() + timedelta(hours=24),
    )
    if booking.version != int(decoded.get("booking_version", 0)):
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": booking.version})
    if booking.status not in {Booking.Status.CONFIRMED, Booking.Status.AWAITING_PAYMENT}:
        raise DomainAPIException("CANCELLATION_NOT_ALLOWED")

    passenger_ids = [str(value) for value in decoded.get("passenger_ids", [])]
    passengers = _selected_passengers(booking, passenger_ids)
    quoted = _quote_payload(booking, passengers)
    for field in (
        "selected_subtotal",
        "selected_discount",
        "selected_fee",
        "selected_total",
        "refund_amount",
        "currency",
    ):
        if str(quoted[field]) != str(decoded.get(field)):
            raise DomainAPIException("CANCELLATION_QUOTE_INVALID")

    lines = {str(line["passenger_id"]): line for line in decoded.get("lines", [])}
    now = timezone.now()
    refunds: list[Refund] = []
    payment_intent = _payment_intent_for_refund(booking)
    for passenger in passengers:
        assignment = (
            SeatAssignment.objects.select_for_update()
            .select_related("trip_seat")
            .filter(
                booking=booking,
                passenger=passenger,
                status=SeatAssignment.Status.ACTIVE,
            )
            .first()
        )
        if assignment is None:
            raise DomainAPIException("CANCELLATION_NOT_ALLOWED")
        before = {
            "passenger": {"status": passenger.status, "boarding_status": passenger.boarding_status},
            "seat_id": str(assignment.trip_seat_id),
            "seat_code": assignment.trip_seat.seat_code,
        }
        assignment.status = SeatAssignment.Status.CANCELLED
        assignment.released_at = now
        assignment.save(update_fields=["status", "released_at"])
        passenger.status = BookingPassenger.Status.CANCELLED
        passenger.cancelled_at = now
        passenger.save(update_fields=["status", "cancelled_at"])
        revoke_tickets_for_passenger(passenger=passenger, reason="passenger_cancelled")
        _store_change(
            booking=booking,
            passenger=passenger,
            change_type=BookingChange.ChangeType.PASSENGER_CANCELLED,
            reason_code=reason_code,
            before=before,
            after={"passenger": {"status": passenger.status}, "seat_status": assignment.status},
            actor=None,
        )
        line = lines[str(passenger.id)]
        requested = money(line["refund_amount"])
        if requested > 0:
            try:
                refunds.append(
                    Refund.objects.create(
                        booking=booking,
                        passenger=passenger,
                        payment_intent=payment_intent,
                        reason_code=reason_code or "customer_cancellation",
                        requested_amount=requested,
                        currency=booking.currency,
                        quote_snapshot=line,
                    )
                )
            except IntegrityError as exc:
                raise DomainAPIException("REFUND_DUPLICATE") from exc

    booking.subtotal_amount = money(booking.subtotal_amount - Decimal(str(decoded["selected_subtotal"])))
    booking.discount_amount = money(booking.discount_amount - Decimal(str(decoded["selected_discount"])))
    booking.fee_amount = money(booking.fee_amount - Decimal(str(decoded["selected_fee"])))
    booking.total_amount = money(booking.subtotal_amount - booking.discount_amount + booking.fee_amount)
    booking.version += 1
    _refresh_grouping_snapshot(booking)
    active_count = booking.passengers.filter(status=BookingPassenger.Status.ACTIVE).count()
    if active_count == 0:
        booking.status = Booking.Status.CANCELLATION_PENDING if refunds else Booking.Status.CANCELLED
        if not refunds:
            booking.cancelled_at = now
        _store_change(
            booking=booking,
            passenger=None,
            change_type=BookingChange.ChangeType.BOOKING_CANCELLED,
            reason_code=reason_code,
            before={"status": Booking.Status.CONFIRMED},
            after={"status": booking.status},
            actor=None,
        )
    booking.save(
        update_fields=[
            "subtotal_amount",
            "discount_amount",
            "fee_amount",
            "total_amount",
            "status",
            "cancelled_at",
            "policy_snapshot",
            "version",
            "updated_at",
        ]
    )
    adjust_commission_after_booking_change(booking)
    OutboxEvent.objects.create(
        aggregate_type="booking",
        aggregate_id=booking.id,
        event_type="booking.cancellation_requested",
        payload={
            "booking_id": booking.public_id,
            "passenger_ids": passenger_ids,
            "refund_ids": [str(refund.id) for refund in refunds],
            "refund_amount": decoded["refund_amount"],
        },
    )
    record_audit(
        action="public.booking.cancel",
        object_type="booking",
        object_id=booking.id,
        actor_type="customer",
        office_id=booking.office_id,
        request=request,
        after={
            "passenger_ids": passenger_ids,
            "status": booking.status,
            "refund_ids": [str(refund.id) for refund in refunds],
        },
    )
    response = _serialize_booking(
        _booking_queryset().get(id=booking.id),
        manage_token=manage_token,
    )
    idempotency.response_status = 200
    idempotency.response_body = {"booking_id": booking.public_id}
    idempotency.locked_until = None
    idempotency.save(update_fields=["response_status", "response_body", "locked_until"])
    return response


def _begin_office_change_idempotency(
    *,
    booking: Booking,
    key: str,
    payload: dict[str, Any],
) -> tuple[IdempotencyKey, bool]:
    fingerprint = _change_fingerprint(payload)
    replay = (
        IdempotencyKey.objects.select_for_update()
        .filter(
            scope_type="office_booking_change",
            scope_id=booking.id,
            key=key,
        )
        .first()
    )
    if replay is not None:
        if replay.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        return replay, True
    return (
        IdempotencyKey.objects.create(
            scope_type="office_booking_change",
            scope_id=booking.id,
            key=key,
            request_hash=fingerprint,
            locked_until=timezone.now() + timedelta(seconds=30),
            expires_at=timezone.now() + timedelta(days=7),
        ),
        False,
    )


def _complete_office_change_idempotency(record: IdempotencyKey, booking: Booking) -> None:
    record.response_status = 200
    record.response_body = {"booking_id": booking.public_id, "version": booking.version}
    record.locked_until = None
    record.save(update_fields=["response_status", "response_body", "locked_until"])


@transaction.atomic
def replace_booking_passenger(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    booking_id: str,
    passenger_id: uuid.UUID,
    data: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    booking = (
        Booking.objects.select_for_update()
        .select_related("trip")
        .filter(
            public_id=booking_id,
            office=context.office,
        )
        .first()
    )
    if booking is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    idempotency, replay = _begin_office_change_idempotency(
        booking=booking,
        key=idempotency_key,
        payload={
            "command": "replace_passenger",
            "passenger_id": str(passenger_id),
            "data": data,
        },
    )
    if replay:
        return _serialize_booking(_booking_queryset().get(id=booking.id))
    if booking.status not in {Booking.Status.CONFIRMED, Booking.Status.AWAITING_PAYMENT}:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    passenger = (
        BookingPassenger.objects.select_for_update()
        .filter(
            id=passenger_id,
            booking=booking,
            status=BookingPassenger.Status.ACTIVE,
        )
        .first()
    )
    if passenger is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if passenger.boarding_status in NON_CANCELLABLE_BOARDING_STATES:
        raise DomainAPIException("PASSENGER_ALREADY_BOARDED")
    assignment = (
        SeatAssignment.objects.select_for_update()
        .select_related("trip_seat")
        .get(
            booking=booking,
            passenger=passenger,
            status=SeatAssignment.Status.ACTIVE,
        )
    )
    new_gender = str(data.get("gender", passenger.gender))
    if new_gender != passenger.gender:
        _assert_gender_adjacency(
            trip=booking.trip,
            selected_seats=[assignment.trip_seat],
            passengers=[{"seat_id": assignment.trip_seat_id, "gender": new_gender}],
            ignore_booking_id=booking.id,
        )
    before = {
        "full_name": passenger.full_name,
        "gender": passenger.gender,
        "passenger_type": passenger.passenger_type,
        "date_of_birth": passenger.date_of_birth.isoformat() if passenger.date_of_birth else None,
        "nationality_code": passenger.nationality_code,
    }
    passenger.full_name = str(data.get("full_name", passenger.full_name)).strip()
    passenger.gender = new_gender
    passenger.passenger_type = str(data.get("passenger_type", passenger.passenger_type))
    passenger.date_of_birth = data.get("date_of_birth", passenger.date_of_birth)
    passenger.nationality_code = data.get("nationality_code", passenger.nationality_code)
    passenger.save(update_fields=["full_name", "gender", "passenger_type", "date_of_birth", "nationality_code"])
    if booking.status == Booking.Status.CONFIRMED:
        reissue_ticket_for_passenger(
            passenger=passenger,
            seat_assignment=assignment,
            reason="passenger_replaced",
        )
    change = _store_change(
        booking=booking,
        passenger=passenger,
        change_type=BookingChange.ChangeType.PASSENGER_REPLACED,
        reason_code=str(data.get("reason_code") or "passenger_replacement"),
        before=before,
        after={
            "full_name": passenger.full_name,
            "gender": passenger.gender,
            "passenger_type": passenger.passenger_type,
            "date_of_birth": passenger.date_of_birth.isoformat() if passenger.date_of_birth else None,
            "nationality_code": passenger.nationality_code,
        },
        actor=actor,
    )
    booking.version += 1
    booking.save(update_fields=["version", "updated_at"])
    OutboxEvent.objects.create(
        aggregate_type="booking_change",
        aggregate_id=change.id,
        event_type="booking.passenger.replaced",
        payload={"booking_id": booking.public_id, "passenger_id": str(passenger.id)},
    )
    _complete_office_change_idempotency(idempotency, booking)
    record_audit(
        action="office.booking.passenger.replace",
        object_type="booking_passenger",
        object_id=passenger.id,
        actor_user=actor,
        office_id=booking.office_id,
        request=request,
        before=before,
        after=change.after_snapshot,
    )
    return _serialize_booking(_booking_queryset().get(id=booking.id))


@transaction.atomic
def change_booking_seat(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    booking_id: str,
    passenger_id: uuid.UUID,
    target_seat_id: uuid.UUID,
    reason_code: str,
    idempotency_key: str,
) -> dict[str, Any]:
    booking = (
        Booking.objects.select_for_update()
        .select_related("trip")
        .filter(
            public_id=booking_id,
            office=context.office,
        )
        .first()
    )
    if booking is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    idempotency, replay = _begin_office_change_idempotency(
        booking=booking,
        key=idempotency_key,
        payload={
            "command": "change_seat",
            "passenger_id": str(passenger_id),
            "target_seat_id": str(target_seat_id),
            "reason_code": reason_code,
        },
    )
    if replay:
        return _serialize_booking(_booking_queryset().get(id=booking.id))
    passenger = (
        BookingPassenger.objects.select_for_update()
        .filter(
            id=passenger_id,
            booking=booking,
            status=BookingPassenger.Status.ACTIVE,
        )
        .first()
    )
    if passenger is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if passenger.boarding_status in NON_CANCELLABLE_BOARDING_STATES:
        raise DomainAPIException("PASSENGER_ALREADY_BOARDED")
    current = (
        SeatAssignment.objects.select_for_update()
        .select_related("trip_seat")
        .get(
            booking=booking,
            passenger=passenger,
            status=SeatAssignment.Status.ACTIVE,
        )
    )
    target = (
        TripSeat.objects.select_for_update()
        .filter(
            id=target_seat_id,
            trip=booking.trip,
            is_current=True,
            sellable=True,
        )
        .first()
    )
    if target is None:
        raise DomainAPIException("SEAT_NOT_AVAILABLE")
    now = timezone.now()
    if (
        SeatAssignment.objects.filter(
            trip=booking.trip,
            trip_seat=target,
            status=SeatAssignment.Status.ACTIVE,
        )
        .exclude(id=current.id)
        .exists()
        or SeatHold.objects.filter(
            trip=booking.trip,
            trip_seat=target,
            status=SeatHold.Status.ACTIVE,
            expires_at__gt=now,
        ).exists()
    ):
        raise DomainAPIException("SEAT_NOT_AVAILABLE")
    _assert_gender_adjacency(
        trip=booking.trip,
        selected_seats=[target],
        passengers=[{"seat_id": target.id, "gender": passenger.gender}],
        ignore_booking_id=booking.id,
    )
    current.status = SeatAssignment.Status.MOVED
    current.released_at = now
    current.save(update_fields=["status", "released_at"])
    try:
        replacement = SeatAssignment.objects.create(
            trip=booking.trip,
            booking=booking,
            passenger=passenger,
            trip_seat=target,
            status=SeatAssignment.Status.ACTIVE,
            price_amount=current.price_amount,
        )
    except IntegrityError as exc:
        raise DomainAPIException("SEAT_NOT_AVAILABLE") from exc
    current.superseded_by = replacement
    current.save(update_fields=["superseded_by"])
    if booking.status == Booking.Status.CONFIRMED:
        reissue_ticket_for_passenger(
            passenger=passenger,
            seat_assignment=replacement,
            reason="seat_changed",
        )
    change = _store_change(
        booking=booking,
        passenger=passenger,
        change_type=BookingChange.ChangeType.SEAT_CHANGED,
        reason_code=reason_code,
        before={"seat_id": str(current.trip_seat_id), "seat_code": current.trip_seat.seat_code},
        after={"seat_id": str(target.id), "seat_code": target.seat_code},
        actor=actor,
    )
    booking.version += 1
    _refresh_grouping_snapshot(booking)
    booking.save(update_fields=["policy_snapshot", "version", "updated_at"])
    OutboxEvent.objects.create(
        aggregate_type="booking_change",
        aggregate_id=change.id,
        event_type="booking.seat.changed",
        payload={
            "booking_id": booking.public_id,
            "passenger_id": str(passenger.id),
            "seat_id": str(target.id),
        },
    )
    _complete_office_change_idempotency(idempotency, booking)
    record_audit(
        action="office.booking.seat.change",
        object_type="seat_assignment",
        object_id=replacement.id,
        actor_user=actor,
        office_id=booking.office_id,
        request=request,
        before=change.before_snapshot,
        after=change.after_snapshot,
    )
    return _serialize_booking(_booking_queryset().get(id=booking.id))
