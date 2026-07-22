from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingPassenger, SeatAssignment
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from common.requests import parse_version
from fleet.models import Driver, SeatLayout, Vehicle
from fleet.services import assert_driver_assignable, assert_vehicle_assignable
from geography.models import Route
from identity.models import User
from organizations.models import Office, OfficeBranch, TransportOperator
from organizations.services import OfficeContext, assert_office_assignable_for_new_trip
from policies.models import ConfigurationValue
from policies.services import effective_configuration, resolve_policy_snapshot
from trips.models import (
    SeatHold,
    Trip,
    TripCancellationAction,
    TripChange,
    TripChangeResponse,
    TripOperationalIssue,
    TripSeat,
    TripStop,
)

ACTIVE_OPERATIONAL_STATUSES = {
    Trip.Status.SCHEDULED,
    Trip.Status.PUBLISHED,
    Trip.Status.BOOKING_OPEN,
    Trip.Status.BOARDING_OPEN,
    Trip.Status.BOARDING_CLOSED,
}
ACTIVE_BOOKING_STATUSES = {
    Booking.Status.AWAITING_PAYMENT,
    Booking.Status.CONFIRMED,
    Booking.Status.CANCELLATION_PENDING,
    Booking.Status.DENIED_BOARDING_REVIEW,
}


@dataclass(frozen=True)
class TripReadiness:
    missing_fields: tuple[str, ...]
    blocking_reasons: tuple[dict[str, object], ...]
    policy_snapshot: dict[str, object]

    @property
    def ready(self) -> bool:
        return not self.missing_fields and not self.blocking_reasons


def _branch(*, office: Office, public_id: str) -> OfficeBranch:
    branch = OfficeBranch.objects.filter(
        public_id=public_id,
        office=office,
        status="active",
    ).first()
    if branch is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "branch_id", "reason": "not_found_or_inactive"}],
        )
    return branch


def _operator(*, office: Office, public_id: str) -> TransportOperator:
    operator = TransportOperator.objects.filter(public_id=public_id).first()
    if operator is None or office.operator_id != operator.id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "operator_id", "reason": "not_owned_by_office"}],
        )
    return operator


def _route(public_id: str) -> Route:
    route = (
        Route.objects.select_related("origin_location", "destination_location")
        .filter(
            public_id=public_id,
            status=Route.Status.ACTIVE,
        )
        .first()
    )
    if route is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "route_id", "reason": "not_found_or_inactive"}],
        )
    return route


def _vehicle(*, office: Office, public_id: str) -> Vehicle:
    vehicle = (
        Vehicle.objects.select_related("seat_layout", "operator")
        .filter(
            public_id=public_id,
            office=office,
        )
        .first()
    )
    if vehicle is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "vehicle_id", "reason": "not_found"}],
        )
    return vehicle


def _driver(*, operator: TransportOperator, public_id: str | None) -> Driver | None:
    if not public_id:
        return None
    driver = Driver.objects.filter(public_id=public_id, operator=operator).first()
    if driver is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "driver_id", "reason": "not_found"}],
        )
    return driver


def _validate_time_window(data: dict[str, Any]) -> None:
    departure = data["scheduled_departure_at"]
    arrival = data.get("scheduled_arrival_at")
    if arrival is not None and arrival <= departure:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "scheduled_arrival_at", "reason": "must_be_after_departure"}],
        )
    for field in ("booking_open_at", "booking_close_at", "boarding_open_at", "boarding_close_at"):
        value = data.get(field)
        if value is not None and value >= departure and field != "boarding_close_at":
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": field, "reason": "must_be_before_departure"}],
            )
    booking_open = data.get("booking_open_at")
    booking_close = data.get("booking_close_at")
    if booking_open and booking_close and booking_open >= booking_close:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "booking_close_at", "reason": "must_be_after_booking_open"}],
        )
    boarding_open = data.get("boarding_open_at")
    boarding_close = data.get("boarding_close_at")
    if boarding_open and boarding_close and boarding_open >= boarding_close:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "boarding_close_at", "reason": "must_be_after_boarding_open"}],
        )


@transaction.atomic
def create_trip(*, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]) -> Trip:
    from subscriptions.services import require_usage_capacity

    require_usage_capacity(context.office, "monthly_trips")
    required = [
        field
        for field in (
            "route_id",
            "branch_id",
            "operator_id",
            "vehicle_id",
            "scheduled_departure_at",
            "currency",
            "base_price",
        )
        if data.get(field) in (None, "")
    ]
    if required:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "required"} for field in required],
        )
    _validate_time_window(data)
    branch = _branch(office=context.office, public_id=str(data["branch_id"]))
    operator = _operator(office=context.office, public_id=str(data["operator_id"]))
    route = _route(str(data["route_id"]))
    vehicle = _vehicle(office=context.office, public_id=str(data["vehicle_id"]))
    driver = _driver(operator=operator, public_id=str(data.get("driver_id") or "") or None)
    currency = str(data["currency"]).strip().upper()
    if len(currency) != 3:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "currency", "reason": "iso_4217_required"}],
        )
    selected_policy_ids = [str(value) for value in data.get("policy_version_ids", [])]
    payment_methods = [str(value) for value in data.get("payment_methods", [])]
    trip = Trip.objects.create(
        office=context.office,
        branch=branch,
        operator=operator,
        route=route,
        vehicle=vehicle,
        driver=driver,
        seat_layout=vehicle.seat_layout,
        scheduled_departure_at=data["scheduled_departure_at"],
        scheduled_arrival_at=data.get("scheduled_arrival_at"),
        currency=currency,
        base_price=data["base_price"],
        booking_open_at=data.get("booking_open_at"),
        booking_close_at=data.get("booking_close_at"),
        boarding_open_at=data.get("boarding_open_at"),
        boarding_close_at=data.get("boarding_close_at"),
        policy_snapshot={"selected_version_ids": selected_policy_ids},
        pricing_snapshot={"payment_methods": payment_methods},
        created_by=actor,
    )
    record_audit(
        action="office.trip.create",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={
            "public_id": trip.public_id,
            "route_id": route.public_id,
            "vehicle_id": vehicle.public_id,
            "driver_id": driver.public_id if driver else None,
            "status": trip.status,
        },
    )
    return trip


def _required_policy_types() -> list[str]:
    raw = getattr(settings, "TRIP_REQUIRED_POLICY_TYPES", "cancellation,payment,boarding")
    return [value.strip() for value in str(raw).split(",") if value.strip()]


def _trip_end(trip: Trip) -> datetime:
    default_hours = int(getattr(settings, "TRIP_DEFAULT_DURATION_HOURS", 8))
    return trip.scheduled_arrival_at or (trip.scheduled_departure_at + timedelta(hours=default_hours))


def _has_resource_overlap(trip: Trip, *, field: str) -> bool:
    start = trip.scheduled_departure_at
    end = _trip_end(trip)
    padding_minutes = int(getattr(settings, "TRIP_RESOURCE_TURNAROUND_MINUTES", 60))
    padded_start = start - timedelta(minutes=padding_minutes)
    padded_end = end + timedelta(minutes=padding_minutes)
    filters: dict[str, object] = {
        "office": trip.office,
        "status__in": ACTIVE_OPERATIONAL_STATUSES,
        "scheduled_departure_at__lt": padded_end,
    }
    value = getattr(trip, f"{field}_id")
    if value is None:
        return False
    filters[field] = value
    candidates = Trip.objects.exclude(id=trip.id).filter(**filters)
    return any(_trip_end(candidate) > padded_start for candidate in candidates)


def check_trip_readiness(trip: Trip) -> TripReadiness:
    missing: list[str] = []
    blockers: list[dict[str, object]] = []
    if trip.base_price <= Decimal("0"):
        missing.append("base_price")
    if not trip.currency or len(trip.currency) != 3:
        missing.append("currency")
    if trip.driver_id is None:
        missing.append("driver_id")
    if trip.booking_open_at is None:
        missing.append("booking_open_at")
    if trip.booking_close_at is None:
        missing.append("booking_close_at")
    if trip.boarding_open_at is None:
        missing.append("boarding_open_at")
    if trip.boarding_close_at is None:
        missing.append("boarding_close_at")

    try:
        assert_office_assignable_for_new_trip(trip.office)
    except DomainAPIException as exc:
        blockers.append({"field": "office", "reason": exc.details})
    if trip.branch.status != "active":
        blockers.append({"field": "branch_id", "reason": "branch_not_active"})
    if trip.operator.status != "active":
        blockers.append({"field": "operator_id", "reason": "operator_not_active"})
    if trip.route.status != Route.Status.ACTIVE:
        blockers.append({"field": "route_id", "reason": "route_not_active"})
    try:
        assert_vehicle_assignable(trip.vehicle, service_date=trip.scheduled_departure_at.date())
    except DomainAPIException as exc:
        blockers.append({"field": "vehicle_id", "reason": exc.details})
    if trip.driver is not None:
        try:
            assert_driver_assignable(trip.driver, service_date=trip.scheduled_departure_at.date())
        except DomainAPIException as exc:
            blockers.append({"field": "driver_id", "reason": exc.details})
    if trip.seat_layout.status != SeatLayout.Status.ACTIVE:
        blockers.append({"field": "seat_layout_id", "reason": "layout_not_active"})
    layout_seat_count = trip.seat_layout.seats.count()
    if layout_seat_count == 0 or layout_seat_count != trip.seat_layout.seat_count:
        blockers.append(
            {
                "field": "seat_layout_id",
                "reason": "layout_seat_count_mismatch",
                "expected": trip.seat_layout.seat_count,
                "actual": layout_seat_count,
            }
        )
    if _has_resource_overlap(trip, field="vehicle"):
        blockers.append({"field": "vehicle_id", "reason": "overlapping_trip"})
    if trip.driver_id is not None and _has_resource_overlap(trip, field="driver"):
        blockers.append({"field": "driver_id", "reason": "overlapping_trip"})

    selected = trip.policy_snapshot.get("selected_version_ids", [])
    policy_snapshot, missing_policy_types = resolve_policy_snapshot(
        office=trip.office,
        selected_ids=selected if isinstance(selected, list) else [],
        required_types=_required_policy_types(),
        at=timezone.now(),
    )
    missing.extend(f"policy:{value}" for value in missing_policy_types)
    return TripReadiness(
        missing_fields=tuple(sorted(set(missing))),
        blocking_reasons=tuple(blockers),
        policy_snapshot=policy_snapshot,
    )


def _create_inventory(trip: Trip) -> None:
    layout_seats = list(trip.seat_layout.seats.all())
    TripSeat.objects.filter(trip=trip).delete()
    TripSeat.objects.bulk_create(
        [
            TripSeat(
                trip=trip,
                layout_seat=seat,
                seat_code=seat.seat_code,
                seat_type=seat.seat_type,
                sellable=seat.is_sellable,
                blocked_reason=None if seat.is_sellable else "layout_not_sellable",
                inventory_version=1,
                is_current=True,
            )
            for seat in layout_seats
        ]
    )


def _create_trip_stops(trip: Trip) -> None:
    stops: list[TripStop] = []
    sequence = 1
    stops.append(
        TripStop(
            trip=trip,
            sequence_no=sequence,
            location=trip.route.origin_location,
            scheduled_at=trip.scheduled_departure_at,
            stop_type=TripStop.StopType.BOARDING,
        )
    )
    sequence += 1
    endpoint_ids = {trip.route.origin_location_id, trip.route.destination_location_id}
    for route_stop in trip.route.stops.select_related("location").all():
        if route_stop.location_id in endpoint_ids:
            continue
        stops.append(
            TripStop(
                trip=trip,
                sequence_no=sequence,
                location=route_stop.location,
                scheduled_at=trip.scheduled_departure_at + timedelta(minutes=route_stop.offset_minutes),
                stop_type=route_stop.stop_type,
            )
        )
        sequence += 1
    stops.append(
        TripStop(
            trip=trip,
            sequence_no=sequence,
            location=trip.route.destination_location,
            scheduled_at=trip.scheduled_arrival_at,
            stop_type=TripStop.StopType.DROPOFF,
        )
    )
    TripStop.objects.filter(trip=trip).delete()
    TripStop.objects.bulk_create(stops)


def _assert_version(trip: Trip, raw_version: object) -> None:
    supplied = parse_version(raw_version)
    if supplied != trip.version:
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": trip.version})


def _emit_trip_event(trip: Trip, event_type: str, payload: dict[str, object] | None = None) -> None:
    OutboxEvent.objects.create(
        aggregate_type="trip",
        aggregate_id=trip.id,
        event_type=event_type,
        payload={"trip_id": trip.public_id, "office_id": trip.office.public_id, **(payload or {})},
    )


@transaction.atomic
def schedule_trip(*, trip: Trip, actor: User, request: HttpRequest | None, version: object) -> Trip:
    trip = (
        Trip.objects.select_for_update(of=("self",))
        .select_related(
            "office",
            "branch",
            "operator",
            "route__origin_location",
            "route__destination_location",
            "vehicle__seat_layout",
            "driver",
            "seat_layout",
        )
        .get(id=trip.id)
    )
    _assert_version(trip, version)
    if trip.status != Trip.Status.DRAFT:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    readiness = check_trip_readiness(trip)
    if not readiness.ready:
        raise DomainAPIException(
            "TRIP_NOT_READY",
            details={
                "missing_fields": list(readiness.missing_fields),
                "blocking_reasons": list(readiness.blocking_reasons),
            },
        )
    before = {"status": trip.status, "version": trip.version}
    configuration = effective_configuration(
        scope_type=ConfigurationValue.ScopeType.OFFICE,
        scope_id=trip.office_id,
    )
    configuration_snapshot = {
        key: {
            "value": item["value"],
            "effective_from": item["effective_from"],
            "source": item["source"],
        }
        for key, item in configuration.items()
        if bool(item.get("snapshot"))
    }
    trip.policy_snapshot = readiness.policy_snapshot
    trip.pricing_snapshot = {
        "currency": trip.currency,
        "base_price": str(trip.base_price),
        "payment_methods": trip.pricing_snapshot.get("payment_methods", []),
        "configuration": configuration_snapshot,
        "captured_at": timezone.now().isoformat(),
    }
    trip.status = Trip.Status.SCHEDULED
    trip.version += 1
    trip.save(update_fields=["policy_snapshot", "pricing_snapshot", "status", "version", "updated_at"])
    _create_inventory(trip)
    _create_trip_stops(trip)
    _emit_trip_event(trip, "trip.scheduled", {"inventory_count": trip.seats.count()})
    record_audit(
        action="office.trip.schedule",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        actor_type="system" if request is None else "user",
        office_id=trip.office_id,
        request=request,
        before=before,
        after={"status": trip.status, "version": trip.version, "inventory_count": trip.seats.count()},
    )
    return trip


@transaction.atomic
def publish_trip(*, trip: Trip, actor: User, request: HttpRequest | None, version: object) -> Trip:
    trip = Trip.objects.select_for_update().select_related("office").get(id=trip.id)
    _assert_version(trip, version)
    if trip.status != Trip.Status.SCHEDULED:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if trip.office.status != Office.Status.ACTIVE:
        raise DomainAPIException("OFFICE_NOT_ACTIVE")
    trip.status = Trip.Status.PUBLISHED
    trip.version += 1
    trip.save(update_fields=["status", "version", "updated_at"])
    _emit_trip_event(trip, "trip.published")
    record_audit(
        action="office.trip.publish",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        actor_type="system" if request is None else "user",
        office_id=trip.office_id,
        request=request,
        after={"status": trip.status, "version": trip.version},
    )
    return trip


def _inventory_is_valid(trip: Trip) -> bool:
    expected = trip.seat_layout.seats.count()
    current = trip.seats.filter(is_current=True)
    actual = current.count()
    unique_codes = current.values("seat_code").distinct().count()
    return expected > 0 and actual == expected and unique_codes == actual


@transaction.atomic
def open_booking(*, trip: Trip, actor: User | None, request: HttpRequest | None, version: object) -> Trip:
    trip = Trip.objects.select_for_update().select_related("seat_layout", "office").get(id=trip.id)
    _assert_version(trip, version)
    if trip.status != Trip.Status.PUBLISHED:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    now = timezone.now()
    if trip.booking_open_at is None or trip.booking_open_at > now:
        raise DomainAPIException("TRIP_NOT_BOOKABLE", details={"reason": "booking_window_not_open"})
    if not _inventory_is_valid(trip):
        raise DomainAPIException("TRIP_INVENTORY_INVALID")
    trip.status = Trip.Status.BOOKING_OPEN
    trip.version += 1
    trip.save(update_fields=["status", "version", "updated_at"])
    _emit_trip_event(trip, "trip.booking_opened")
    record_audit(
        action="trip.open_booking",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        actor_type="system" if actor is None else "user",
        office_id=trip.office_id,
        request=request,
        after={"status": trip.status, "version": trip.version},
    )
    return trip


@transaction.atomic
def open_due_trip_bookings(*, now: datetime | None = None) -> int:
    current = now or timezone.now()
    ids = list(
        Trip.objects.filter(
            status=Trip.Status.PUBLISHED,
            booking_open_at__isnull=False,
            booking_open_at__lte=current,
        ).values_list("id", flat=True)
    )
    opened = 0
    for trip_id in ids:
        trip = Trip.objects.select_for_update().filter(id=trip_id).first()
        if trip is None or trip.status != Trip.Status.PUBLISHED:
            continue
        try:
            open_booking(trip=trip, actor=None, request=None, version=trip.version)
        except DomainAPIException as exc:
            if exc.code in {"STATE_TRANSITION_NOT_ALLOWED", "TRIP_NOT_BOOKABLE"}:
                continue
            raise
        opened += 1
    return opened


def _material_change(
    *, trip: Trip, changes: dict[str, object]
) -> tuple[bool, str, dict[str, object], dict[str, object]]:
    previous: dict[str, object] = {}
    updated: dict[str, object] = {}
    types: list[str] = []
    threshold = int(getattr(settings, "TRIP_MATERIAL_CHANGE_MINUTES", 30))
    if "scheduled_departure_at" in changes:
        new_departure = cast(datetime, changes["scheduled_departure_at"])
        previous["scheduled_departure_at"] = trip.scheduled_departure_at.isoformat()
        updated["scheduled_departure_at"] = new_departure.isoformat()
        delta = abs((new_departure - trip.scheduled_departure_at).total_seconds()) / 60
        if delta >= threshold:
            types.append(TripChange.ChangeType.TIME)
    if "base_price" in changes:
        new_price = Decimal(str(changes["base_price"]))
        if new_price != trip.base_price:
            previous["base_price"] = str(trip.base_price)
            updated["base_price"] = str(new_price)
            types.append(TripChange.ChangeType.PRICE)
    if "vehicle" in changes:
        new_vehicle = cast(Vehicle, changes["vehicle"])
        if new_vehicle != trip.vehicle:
            previous["vehicle_id"] = trip.vehicle.public_id
            updated["vehicle_id"] = new_vehicle.public_id
            types.append(TripChange.ChangeType.VEHICLE)
    change_type = types[0] if len(types) == 1 else TripChange.ChangeType.MULTIPLE
    return bool(types), change_type, previous, updated


def _active_bookings(trip: Trip) -> QuerySet[Booking]:
    return Booking.objects.filter(trip=trip, status__in=ACTIVE_BOOKING_STATUSES)


@transaction.atomic
def update_trip(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    trip_id: str,
    data: dict[str, Any],
) -> Trip:
    trip = (
        Trip.objects.select_for_update()
        .select_related("vehicle", "office")
        .filter(
            public_id=trip_id,
            office=context.office,
        )
        .first()
    )
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    _assert_version(trip, data.get("version"))
    if trip.status in {
        Trip.Status.DEPARTED,
        Trip.Status.ARRIVED,
        Trip.Status.COMPLETED,
        Trip.Status.CANCELLED,
        Trip.Status.INTERRUPTED,
    }:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")

    changes: dict[str, object] = {}
    if "scheduled_departure_at" in data:
        changes["scheduled_departure_at"] = data["scheduled_departure_at"]
    if "scheduled_arrival_at" in data:
        changes["scheduled_arrival_at"] = data["scheduled_arrival_at"]
    if "base_price" in data:
        changes["base_price"] = data["base_price"]
    if "vehicle_id" in data:
        changes["vehicle"] = _vehicle(office=context.office, public_id=str(data["vehicle_id"]))
    if "driver_id" in data:
        changes["driver"] = _driver(
            operator=trip.operator,
            public_id=str(data.get("driver_id") or "") or None,
        )
    if not changes:
        return trip

    bookings = _active_bookings(trip)
    has_bookings = bookings.exists()
    material, change_type, previous_snapshot, new_snapshot = _material_change(trip=trip, changes=changes)
    if has_bookings and "vehicle" in changes:
        raise DomainAPIException(
            "STATE_TRANSITION_NOT_ALLOWED",
            details={"reason": "vehicle_change_requires_reallocation_workflow"},
        )
    if has_bookings and "base_price" in changes:
        # Existing bookings retain their immutable price snapshots. The trip price may change only
        # through a material change record so customers are never silently repriced.
        material = True

    old_departure = trip.scheduled_departure_at
    if "vehicle" in changes:
        new_vehicle = cast(Vehicle, changes["vehicle"])
        trip.vehicle = new_vehicle
        trip.seat_layout = new_vehicle.seat_layout
    if "driver" in changes:
        trip.driver = cast(Driver | None, changes["driver"])
    if "scheduled_departure_at" in changes:
        trip.scheduled_departure_at = cast(datetime, changes["scheduled_departure_at"])
    if "scheduled_arrival_at" in changes:
        trip.scheduled_arrival_at = cast(datetime | None, changes["scheduled_arrival_at"])
    if "base_price" in changes:
        trip.base_price = Decimal(str(changes["base_price"]))
    _validate_time_window(
        {
            "scheduled_departure_at": trip.scheduled_departure_at,
            "scheduled_arrival_at": trip.scheduled_arrival_at,
            "booking_open_at": trip.booking_open_at,
            "booking_close_at": trip.booking_close_at,
            "boarding_open_at": trip.boarding_open_at,
            "boarding_close_at": trip.boarding_close_at,
        }
    )
    trip.version += 1
    trip.save()

    if trip.status == Trip.Status.DRAFT and "vehicle" in changes:
        trip.policy_snapshot = {
            **trip.policy_snapshot,
            "selected_version_ids": trip.policy_snapshot.get("selected_version_ids", []),
        }
        trip.save(update_fields=["policy_snapshot", "updated_at"])
    if old_departure != trip.scheduled_departure_at and trip.stops.exists():
        delta = trip.scheduled_departure_at - old_departure
        for stop in trip.stops.select_for_update().all():
            if stop.scheduled_at is not None:
                stop.scheduled_at += delta
                stop.save(update_fields=["scheduled_at"])

    if material and has_bookings:
        response_hours = int(getattr(settings, "TRIP_CHANGE_RESPONSE_HOURS", 24))
        change = TripChange.objects.create(
            trip=trip,
            change_type=change_type,
            classification=TripChange.Classification.MATERIAL,
            previous_snapshot=previous_snapshot,
            new_snapshot=new_snapshot,
            response_deadline_at=min(
                timezone.now() + timedelta(hours=response_hours),
                trip.scheduled_departure_at,
            ),
            created_by=actor,
        )
        response_objects = [TripChangeResponse(change=change, booking=booking) for booking in bookings]
        TripChangeResponse.objects.bulk_create(response_objects)
        for booking in bookings:
            OutboxEvent.objects.create(
                aggregate_type="trip_change",
                aggregate_id=change.id,
                event_type="notification.requested",
                payload={
                    "template": "trip_material_change_response_required",
                    "trip_id": trip.public_id,
                    "booking_id": booking.public_id,
                    "change_id": str(change.id),
                },
            )
    elif previous_snapshot or new_snapshot:
        TripChange.objects.create(
            trip=trip,
            change_type=change_type,
            classification=TripChange.Classification.MINOR,
            previous_snapshot=previous_snapshot,
            new_snapshot=new_snapshot,
            created_by=actor,
        )

    _emit_trip_event(trip, "trip.updated", {"material": material and has_bookings})
    record_audit(
        action="office.trip.update",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before={**previous_snapshot, "version": trip.version - 1},
        after={**new_snapshot, "version": trip.version},
    )
    return trip


def _departure_blockers(trip: Trip) -> list[dict[str, object]]:
    blockers: list[dict[str, object]] = []
    duplicates = (
        SeatAssignment.objects.filter(trip=trip, status=SeatAssignment.Status.ACTIVE)
        .values("trip_seat_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    if duplicates.exists():
        blockers.append({"type": "duplicate_seat_assignment"})
    missing_seat = BookingPassenger.objects.filter(
        booking__trip=trip,
        booking__status=Booking.Status.CONFIRMED,
    ).exclude(seat_assignments__status=SeatAssignment.Status.ACTIVE)
    if missing_seat.exists():
        blockers.append({"type": "passenger_without_seat", "count": missing_seat.count()})
    if Booking.objects.filter(trip=trip, status=Booking.Status.DENIED_BOARDING_REVIEW).exists():
        blockers.append({"type": "urgent_booking_case"})
    for issue in trip.operational_issues.filter(status=TripOperationalIssue.Status.OPEN):
        blockers.append({"type": issue.issue_type, "issue_id": str(issue.id)})
    try:
        assert_vehicle_assignable(trip.vehicle, service_date=timezone.localdate())
    except DomainAPIException:
        blockers.append({"type": "vehicle_unavailable"})
    if trip.driver is None:
        blockers.append({"type": "driver_missing"})
    else:
        try:
            assert_driver_assignable(trip.driver, service_date=timezone.localdate())
        except DomainAPIException:
            blockers.append({"type": "driver_unavailable"})
    return blockers


@transaction.atomic
def command_trip(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    trip_id: str,
    data: dict[str, Any],
) -> Trip:
    trip = (
        Trip.objects.select_for_update(of=("self",))
        .select_related(
            "office",
            "branch",
            "operator",
            "route__origin_location",
            "route__destination_location",
            "vehicle__seat_layout",
            "driver",
            "seat_layout",
        )
        .filter(public_id=trip_id, office=context.office)
        .first()
    )
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    command = str(data["command"])
    version = data.get("version")
    if command == "schedule":
        return schedule_trip(trip=trip, actor=actor, request=request, version=version)
    if command == "publish":
        return publish_trip(trip=trip, actor=actor, request=request, version=version)
    if command == "open_booking":
        return open_booking(trip=trip, actor=actor, request=request, version=version)
    if command == "interrupt":
        from trips.reallocation_services import interrupt_trip

        return interrupt_trip(
            context=context,
            actor=actor,
            request=request,
            trip_id=trip_id,
            version=parse_version(version),
            reason_code=str(data.get("reason_code") or ""),
        )

    _assert_version(trip, version)
    before_status = trip.status
    now = timezone.now()
    if command == "open_boarding":
        if trip.status != Trip.Status.BOOKING_OPEN:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if trip.boarding_open_at is None or trip.boarding_open_at > now:
            raise DomainAPIException("BOARDING_TOO_EARLY")
        trip.status = Trip.Status.BOARDING_OPEN
    elif command == "close_boarding":
        if trip.status != Trip.Status.BOARDING_OPEN:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        urgent = trip.operational_issues.filter(
            status=TripOperationalIssue.Status.OPEN,
            issue_type=TripOperationalIssue.IssueType.URGENT_CASE,
        ).exists()
        if urgent:
            raise DomainAPIException("URGENT_CASE_OPEN")
        trip.status = Trip.Status.BOARDING_CLOSED
    elif command == "depart":
        if trip.status != Trip.Status.BOARDING_CLOSED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        blockers = _departure_blockers(trip)
        if blockers:
            raise DomainAPIException("TRIP_DEPARTURE_BLOCKED", details={"blockers": blockers})
        trip.status = Trip.Status.DEPARTED
        trip.actual_departure_at = now
    elif command == "arrive":
        if trip.status != Trip.Status.DEPARTED:
            raise DomainAPIException("TRIP_NOT_DEPARTED")
        trip.status = Trip.Status.ARRIVED
        trip.actual_arrival_at = now
    elif command == "complete":
        if trip.status != Trip.Status.ARRIVED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if Booking.objects.filter(
            trip=trip,
            status__in=[Booking.Status.DENIED_BOARDING_REVIEW, Booking.Status.CANCELLATION_PENDING],
        ).exists():
            raise DomainAPIException("TRIP_UNRESOLVED_CASES")
        trip.status = Trip.Status.COMPLETED
    elif command == "cancel":
        if trip.status not in ACTIVE_OPERATIONAL_STATUSES:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        reason = str(data.get("reason_code") or "").strip()
        if not reason:
            raise DomainAPIException("TRIP_CANCEL_REASON_REQUIRED")
        trip.status = Trip.Status.CANCELLED
        trip.booking_close_at = now
        trip.seats.filter(is_current=True).update(sellable=False, blocked_reason="trip_cancelled")
        affected = list(_active_bookings(trip).select_for_update())
        TripCancellationAction.objects.bulk_create(
            [TripCancellationAction(trip=trip, booking=booking, reason_code=reason) for booking in affected],
            ignore_conflicts=True,
        )
        Booking.objects.filter(id__in=[booking.id for booking in affected]).update(
            status=Booking.Status.CANCELLATION_PENDING
        )
        for booking in affected:
            OutboxEvent.objects.create(
                aggregate_type="trip_cancellation",
                aggregate_id=trip.id,
                event_type="trip.cancellation_action_required",
                payload={
                    "trip_id": trip.public_id,
                    "booking_id": booking.public_id,
                    "reason_code": reason,
                    "actions": ["offer_alternative", "start_refund"],
                },
            )
    else:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "command", "reason": "unsupported"}],
        )

    trip.version += 1
    trip.save()
    if command == "complete":
        from finance.services import recognize_trip_financials

        recognize_trip_financials(trip_id=trip.id)
    if command in {"close_boarding", "depart"}:
        from boarding.models import TripManifest
        from boarding.services import generate_manifest

        manifest_status = (
            TripManifest.Status.BOARDING_CLOSED if command == "close_boarding" else TripManifest.Status.FINAL
        )
        generate_manifest(trip=trip, status=manifest_status, actor=actor)
    _emit_trip_event(trip, f"trip.{command}", {"previous_status": before_status})
    record_audit(
        action=f"office.trip.{command}",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before={"status": before_status, "version": trip.version - 1},
        after={"status": trip.status, "version": trip.version},
        reason_code=str(data.get("reason_code") or "") or None,
    )
    return trip


def seat_map_for_trip(trip: Trip, *, session_id: uuid.UUID | None = None) -> list[dict[str, object]]:
    now = timezone.now()
    assignment_ids = set(
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
    results: list[dict[str, object]] = []
    for seat in trip.seats.filter(is_current=True).select_related("layout_seat").all():
        status = "available"
        hold = holds.get(seat.id)
        if not seat.sellable:
            status = "blocked"
        elif seat.id in assignment_ids:
            status = "unavailable"
        elif hold is not None:
            status = "held_by_you" if hold.owner_session_id == session_id else "unavailable"
        results.append(
            {
                "id": str(seat.id),
                "code": seat.seat_code,
                "row": seat.layout_seat.row_no,
                "column": seat.layout_seat.column_no,
                "type": seat.seat_type,
                "status": status,
                "price": str(trip.base_price) if status in {"available", "held_by_you"} else None,
            }
        )
    return results
