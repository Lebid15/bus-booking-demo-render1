from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db.models import Q, QuerySet
from django.utils import timezone

from bookings.models import SeatAssignment
from common.exceptions import DomainAPIException
from geography.models import Location, Route
from organizations.models import Office
from trips.models import SeatHold, Trip, TripSeat
from trips.pricing import cancellation_summary, honest_from_price, payment_methods

PUBLIC_OFFICE_STATUSES = {Office.Status.ACTIVE, Office.Status.CONDITIONAL}


def _office_zone(office: Office) -> ZoneInfo:
    try:
        return ZoneInfo(office.timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _parse_service_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "date", "reason": "iso_date_required"}],
        ) from exc


def _parse_passengers(raw: object) -> int:
    try:
        count = int(str(raw or 1))
    except (TypeError, ValueError) as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "passengers", "reason": "integer_required"}],
        ) from exc
    if count < 1 or count > 8:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "passengers", "reason": "range_1_8"}],
        )
    return count


def assert_public_bookable(trip: Trip, *, now: datetime | None = None) -> None:
    current = now or timezone.now()
    reason: str | None = None
    if trip.status != Trip.Status.BOOKING_OPEN:
        reason = "trip_status_not_open"
    elif trip.office.status not in PUBLIC_OFFICE_STATUSES:
        reason = "office_not_accepting_new_bookings"
    elif trip.booking_open_at is not None and trip.booking_open_at > current:
        reason = "booking_window_not_open"
    elif trip.booking_close_at is not None and trip.booking_close_at <= current:
        reason = "booking_window_closed"
    elif trip.scheduled_departure_at <= current:
        reason = "trip_departed_or_due"
    if reason is None:
        from subscriptions.services import commercial_access

        subscription_access = commercial_access(trip.office, now=current)
        if not subscription_access["allowed"]:
            reason = str(subscription_access["reason"] or "subscription_restricted")
    if reason is not None:
        raise DomainAPIException("TRIP_NOT_BOOKABLE", details={"reason": reason})


def _active_hold_query(now: datetime) -> Q:
    return Q(holds__status=SeatHold.Status.ACTIVE, holds__expires_at__gt=now)


def available_seat_ids(trip: Trip, *, now: datetime | None = None) -> set[uuid.UUID]:
    current = now or timezone.now()
    assigned = set(
        SeatAssignment.objects.filter(
            trip=trip,
            status=SeatAssignment.Status.ACTIVE,
        ).values_list("trip_seat_id", flat=True)
    )
    held = set(
        SeatHold.objects.filter(
            trip=trip,
            status=SeatHold.Status.ACTIVE,
            expires_at__gt=current,
        ).values_list("trip_seat_id", flat=True)
    )
    return set(
        TripSeat.objects.filter(trip=trip, is_current=True, sellable=True)
        .exclude(id__in=assigned | held)
        .values_list("id", flat=True)
    )


def _public_policy_summaries(trip: Trip) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for policy_type, raw in trip.policy_snapshot.items():
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("code"):
            continue
        rules = raw.get("rules", {})
        summary = rules.get("summary") if isinstance(rules, dict) else None
        summaries.append(
            {
                "id": str(raw["id"]),
                "code": str(raw["code"]),
                "policy_type": str(policy_type),
                "title": str(raw.get("title") or raw["code"]),
                "summary": str(summary or raw.get("title") or "راجع النص الكامل للسياسة."),
                "version_no": int(raw.get("version_no") or 1),
                "language": str(raw.get("language") or "ar"),
            }
        )
    return sorted(summaries, key=lambda item: str(item["policy_type"]))


def _trip_payload(trip: Trip, *, available_count: int) -> dict[str, object]:
    return {
        "id": trip.public_id,
        "office": {"id": trip.office.public_id, "name": trip.office.trade_name},
        "operator": {
            "id": trip.operator.public_id,
            "name": trip.operator.trade_name or trip.operator.legal_name,
        },
        "origin": {
            "id": trip.route.origin_location.public_id,
            "name": trip.route.origin_location.name_ar,
            "type": trip.route.origin_location.location_type,
            "address": trip.route.origin_location.address_text,
        },
        "destination": {
            "id": trip.route.destination_location.public_id,
            "name": trip.route.destination_location.name_ar,
            "type": trip.route.destination_location.location_type,
            "address": trip.route.destination_location.address_text,
        },
        "departure_at": trip.scheduled_departure_at,
        "arrival_at": trip.scheduled_arrival_at,
        "currency": trip.currency,
        "from_price": str(honest_from_price(trip)),
        "available_seats": available_count,
        "payment_methods": payment_methods(trip),
        "cancellation_summary": cancellation_summary(trip),
        "quote_version": trip.version,
        "policy_summaries": _public_policy_summaries(trip),
    }


def _base_public_queryset() -> QuerySet[Trip]:
    return (
        Trip.objects.select_related(
            "office",
            "operator",
            "route__origin_location",
            "route__destination_location",
            "seat_layout",
        )
        .prefetch_related("seats__layout_seat")
        .filter(
            status=Trip.Status.BOOKING_OPEN,
            office__status__in=PUBLIC_OFFICE_STATUSES,
            route__status=Route.Status.ACTIVE,
            route__origin_location__status=Location.Status.ACTIVE,
            route__destination_location__status=Location.Status.ACTIVE,
        )
    )


def search_public_trips(
    *, origin_id: str, destination_id: str, service_date_raw: str, passengers_raw: object
) -> list[dict[str, object]]:
    if not origin_id or not destination_id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[
                {"field": "origin_id", "reason": "required"},
                {"field": "destination_id", "reason": "required"},
            ],
        )
    if origin_id == destination_id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "destination_id", "reason": "must_differ_from_origin"}],
        )
    service_date = _parse_service_date(service_date_raw)
    passenger_count = _parse_passengers(passengers_raw)
    now = timezone.now()
    # Broad UTC window first, then exact office-local date filtering below.
    broad_start = timezone.make_aware(datetime.combine(service_date - timedelta(days=1), time.min))
    broad_end = timezone.make_aware(datetime.combine(service_date + timedelta(days=2), time.min))
    queryset = (
        _base_public_queryset()
        .filter(
            route__origin_location__public_id=origin_id,
            route__destination_location__public_id=destination_id,
            scheduled_departure_at__gte=max(now, broad_start),
            scheduled_departure_at__lt=broad_end,
        )
        .filter(Q(booking_close_at__isnull=True) | Q(booking_close_at__gt=now))
    )

    results: list[dict[str, object]] = []
    for trip in queryset.order_by("scheduled_departure_at", "public_id"):
        from subscriptions.services import commercial_access

        if not commercial_access(trip.office, now=now)["allowed"]:
            continue
        local_departure = trip.scheduled_departure_at.astimezone(_office_zone(trip.office))
        if local_departure.date() != service_date:
            continue
        available_count = len(available_seat_ids(trip, now=now))
        if available_count < passenger_count:
            continue
        results.append(_trip_payload(trip, available_count=available_count))
    return results


def get_public_trip(trip_id: str) -> tuple[Trip, dict[str, object]]:
    trip = _base_public_queryset().filter(public_id=trip_id).first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    assert_public_bookable(trip)
    return trip, _trip_payload(trip, available_count=len(available_seat_ids(trip)))


def parse_hold_token(token: str) -> tuple[uuid.UUID, str] | None:
    batch_text, separator, secret = token.partition(".")
    if not separator or len(secret) < 32:
        return None
    try:
        return uuid.UUID(batch_text), secret
    except ValueError:
        return None


def hold_hash(token: str, trip_seat_id: uuid.UUID) -> bytes:
    return hashlib.sha256(f"{token}:{trip_seat_id}".encode()).digest()


def hold_belongs_to_token(hold: SeatHold, token: str, batch_id: uuid.UUID) -> bool:
    return hold.owner_booking_draft_id == batch_id and bytes(hold.hold_token_hash) == hold_hash(
        token, hold.trip_seat_id
    )


def public_seat_map(trip: Trip, *, hold_token: str | None = None) -> dict[str, object]:
    assert_public_bookable(trip)
    now = timezone.now()
    token_parts = parse_hold_token(hold_token or "") if hold_token else None
    batch_id = token_parts[0] if token_parts else None
    assigned = set(
        SeatAssignment.objects.filter(
            trip=trip,
            status=SeatAssignment.Status.ACTIVE,
        ).values_list("trip_seat_id", flat=True)
    )
    holds = {
        hold.trip_seat_id: hold
        for hold in SeatHold.objects.filter(
            trip=trip,
            status=SeatHold.Status.ACTIVE,
            expires_at__gt=now,
        )
    }
    seats: list[dict[str, object]] = []
    owned_expiry: datetime | None = None
    for seat in trip.seats.filter(is_current=True).select_related("layout_seat").all():
        status = "available"
        hold = holds.get(seat.id)
        if not seat.sellable:
            status = "blocked"
        elif seat.id in assigned:
            status = "unavailable"
        elif hold is not None:
            owned = bool(batch_id and hold_token and hold_belongs_to_token(hold, hold_token, batch_id))
            status = "held_by_you" if owned else "unavailable"
            if owned and (owned_expiry is None or hold.expires_at < owned_expiry):
                owned_expiry = hold.expires_at
        seats.append(
            {
                "id": str(seat.id),
                "code": seat.seat_code,
                "row": seat.layout_seat.row_no,
                "column": seat.layout_seat.column_no,
                "type": seat.seat_type,
                "status": status,
                "price": str(honest_from_price(trip)) if status in {"available", "held_by_you"} else None,
            }
        )
    return {
        "trip_id": trip.public_id,
        "layout_version": trip.seat_layout.version,
        "expires_at": owned_expiry,
        "seats": seats,
    }
