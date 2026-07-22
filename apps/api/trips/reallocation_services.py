from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import manage_token_matches
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import IdempotencyKey, OutboxEvent
from fleet.models import SeatAdjacency, SeatLayoutSeat, Vehicle
from fleet.services import assert_vehicle_assignable
from identity.models import User
from organizations.services import OfficeContext
from tickets.services import reissue_ticket_for_passenger
from trips.models import (
    SeatHold,
    Trip,
    TripChange,
    TripChangeResponse,
    TripInterruptionResolution,
    TripOperationalIssue,
    TripReallocationLine,
    TripReallocationPlan,
    TripSeat,
)


@dataclass(frozen=True)
class AssignmentInput:
    assignment: SeatAssignment
    passenger: BookingPassenger
    old_layout_seat: SeatLayoutSeat


@dataclass(frozen=True)
class Candidate:
    seats: tuple[SeatLayoutSeat, ...]
    score: int


def _fingerprint(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _begin_idempotency(
    *, scope: str, scope_id: uuid.UUID, key: str, payload: object
) -> tuple[IdempotencyKey, dict[str, Any] | None]:
    fingerprint = _fingerprint(payload)
    record = IdempotencyKey.objects.select_for_update().filter(scope_type=scope, scope_id=scope_id, key=key).first()
    if record is None:
        record = IdempotencyKey.objects.create(
            scope_type=scope,
            scope_id=scope_id,
            key=key,
            request_hash=fingerprint,
            locked_until=timezone.now() + timedelta(seconds=45),
            expires_at=timezone.now() + timedelta(hours=24),
        )
    if record.request_hash != fingerprint:
        raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
    return record, dict(record.response_body) if record.response_body is not None else None


def _complete_idempotency(record: IdempotencyKey, response: dict[str, Any]) -> None:
    record.response_status = 200
    record.response_body = json.loads(json.dumps(response, default=str))
    record.locked_until = None
    record.save(update_fields=["response_status", "response_body", "locked_until"])


def _seat_rank(seat_type: str) -> int:
    return {"blocked": 0, "crew": 0, "standard": 1, "accessible": 1, "single": 2, "vip": 3}.get(seat_type, 1)


def _seat_score(old: SeatLayoutSeat, new: SeatLayoutSeat) -> int:
    distance = abs(old.row_no - new.row_no) + abs(old.column_no - new.column_no)
    score = -distance
    if old.seat_code == new.seat_code:
        score += 80
    if old.seat_type == new.seat_type:
        score += 60
    elif _seat_rank(new.seat_type) >= _seat_rank(old.seat_type):
        score += 25
    else:
        score -= 80
    return score


def _protected_units(assignments: list[AssignmentInput]) -> list[list[AssignmentInput]]:
    by_booking: dict[uuid.UUID, list[AssignmentInput]] = {}
    for item in assignments:
        by_booking.setdefault(item.passenger.booking_id, []).append(item)
    units: list[list[AssignmentInput]] = []
    used: set[uuid.UUID] = set()
    for booking_items in by_booking.values():
        booking = booking_items[0].passenger.booking
        by_sequence = {item.passenger.sequence_no: item for item in booking_items}
        grouping = booking.policy_snapshot.get("passenger_grouping", {})
        groups = grouping.get("protected_groups", []) if isinstance(grouping, dict) else []
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                guardian = by_sequence.get(int(group.get("guardian_sequence", -1)))
                dependent = by_sequence.get(int(group.get("dependent_sequence", -1)))
                if guardian and dependent and guardian.passenger.id not in used and dependent.passenger.id not in used:
                    units.append([guardian, dependent])
                    used.update({guardian.passenger.id, dependent.passenger.id})
    for item in assignments:
        if item.passenger.id not in used:
            units.append([item])
    units.sort(key=lambda unit: (-len(unit), unit[0].passenger.booking.pnr, unit[0].passenger.sequence_no))
    return units


def _adjacency_pairs(layout_id: uuid.UUID) -> list[tuple[SeatLayoutSeat, SeatLayoutSeat]]:
    rows = SeatAdjacency.objects.filter(
        layout_id=layout_id,
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
        seat_a__is_sellable=True,
        seat_b__is_sellable=True,
    ).select_related("seat_a", "seat_b")
    return [(row.seat_a, row.seat_b) for row in rows]


def _adjacency_map(layout_id: uuid.UUID) -> dict[uuid.UUID, set[uuid.UUID]]:
    result: dict[uuid.UUID, set[uuid.UUID]] = {}
    for first, second in _adjacency_pairs(layout_id):
        result.setdefault(first.id, set()).add(second.id)
        result.setdefault(second.id, set()).add(first.id)
    return result


def _unit_candidates(
    unit: list[AssignmentInput], target_seats: list[SeatLayoutSeat], pairs: list[tuple[SeatLayoutSeat, SeatLayoutSeat]]
) -> list[Candidate]:
    if len(unit) == 1:
        old = unit[0].old_layout_seat
        return [
            Candidate((seat,), _seat_score(old, seat))
            for seat in sorted(target_seats, key=lambda seat: (-_seat_score(old, seat), seat.row_no, seat.column_no))
        ]
    if len(unit) == 2:
        first, second = unit
        candidates: list[Candidate] = []
        for left, right in pairs:
            direct = _seat_score(first.old_layout_seat, left) + _seat_score(second.old_layout_seat, right) + 120
            reverse = _seat_score(first.old_layout_seat, right) + _seat_score(second.old_layout_seat, left) + 120
            candidates.append(Candidate((left, right), direct))
            candidates.append(Candidate((right, left), reverse))
        return sorted(candidates, key=lambda item: (-item.score, tuple(seat.seat_code for seat in item.seats)))
    return []


def _gender_allowed(
    unit: list[AssignmentInput],
    seats: tuple[SeatLayoutSeat, ...],
    assigned: dict[uuid.UUID, tuple[AssignmentInput, SeatLayoutSeat]],
    adjacency: dict[uuid.UUID, set[uuid.UUID]],
) -> bool:
    proposed = list(zip(unit, seats, strict=True))
    for item, seat in proposed:
        for _, (other, other_seat) in assigned.items():
            if other_seat.id not in adjacency.get(seat.id, set()):
                continue
            if other.passenger.booking_id == item.passenger.booking_id:
                continue
            if other.passenger.gender != item.passenger.gender:
                return False
    for index, (item, seat) in enumerate(proposed):
        for other, other_seat in proposed[index + 1 :]:
            if other_seat.id not in adjacency.get(seat.id, set()):
                continue
            if (
                other.passenger.booking_id != item.passenger.booking_id
                and other.passenger.gender != item.passenger.gender
            ):
                return False
    return True


def _solve(
    assignments: list[AssignmentInput], target_layout_id: uuid.UUID
) -> tuple[dict[uuid.UUID, tuple[SeatLayoutSeat, int]], list[uuid.UUID]]:
    target_seats = list(
        SeatLayoutSeat.objects.filter(layout_id=target_layout_id, is_sellable=True).order_by(
            "row_no", "column_no", "seat_code"
        )
    )
    units = _protected_units(assignments)
    pairs = _adjacency_pairs(target_layout_id)
    adjacency = _adjacency_map(target_layout_id)
    used: set[uuid.UUID] = set()
    assigned: dict[uuid.UUID, tuple[AssignmentInput, SeatLayoutSeat]] = {}
    scores: dict[uuid.UUID, int] = {}

    def backtrack(index: int) -> bool:
        if index >= len(units):
            return True
        unit = units[index]
        for candidate in _unit_candidates(unit, target_seats, pairs):
            if any(seat.id in used for seat in candidate.seats):
                continue
            if not _gender_allowed(unit, candidate.seats, assigned, adjacency):
                continue
            for item, seat in zip(unit, candidate.seats, strict=True):
                used.add(seat.id)
                assigned[item.passenger.id] = (item, seat)
                scores[item.passenger.id] = _seat_score(item.old_layout_seat, seat)
            if backtrack(index + 1):
                return True
            for item, seat in zip(unit, candidate.seats, strict=True):
                used.remove(seat.id)
                assigned.pop(item.passenger.id, None)
                scores.pop(item.passenger.id, None)
        return False

    if not backtrack(0):
        return {}, [item.passenger.id for item in assignments]
    return {pid: (seat, scores[pid]) for pid, (_, seat) in assigned.items()}, []


def serialize_plan(plan: TripReallocationPlan) -> dict[str, Any]:
    lines = list(plan.lines.select_related("passenger__booking", "target_layout_seat").all())
    return {
        "id": str(plan.id),
        "trip_id": plan.trip.public_id,
        "status": plan.status,
        "trip_version": plan.trip_version,
        "source_inventory_version": plan.source_inventory_version,
        "target_inventory_version": plan.target_inventory_version,
        "previous_vehicle_id": plan.previous_vehicle.public_id,
        "target_vehicle_id": plan.target_vehicle.public_id,
        "conflict_count": plan.conflict_count,
        "lines": [
            {
                "passenger_id": str(line.passenger_id),
                "pnr": line.passenger.booking.pnr,
                "old_seat_code": line.old_seat_code,
                "target_seat_code": line.target_seat_code,
                "status": line.status,
                "conflict_code": line.conflict_code,
                "score": line.score,
            }
            for line in lines
        ],
        "simulation": plan.simulation,
        "created_at": plan.created_at,
        "applied_at": plan.applied_at,
    }


@transaction.atomic
def preview_vehicle_reallocation(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    trip_id: str,
    target_vehicle_id: str,
    version: int,
    idempotency_key: str,
) -> TripReallocationPlan:
    trip = (
        Trip.objects.select_for_update()
        .select_related("vehicle", "seat_layout", "office")
        .filter(public_id=trip_id, office=context.office)
        .first()
    )
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    record, replay = _begin_idempotency(
        scope="trip_reallocation_preview",
        scope_id=trip.id,
        key=idempotency_key,
        payload={"target_vehicle_id": target_vehicle_id, "version": version},
    )
    if replay is not None:
        return TripReallocationPlan.objects.get(id=replay["plan_id"])
    if trip.version != version:
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": trip.version})
    if trip.status not in {
        Trip.Status.SCHEDULED,
        Trip.Status.PUBLISHED,
        Trip.Status.BOOKING_OPEN,
        Trip.Status.BOARDING_OPEN,
    }:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if BookingPassenger.objects.filter(
        booking__trip=trip, boarding_status=BookingPassenger.BoardingStatus.BOARDED
    ).exists():
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED", details={"reason": "passenger_already_boarded"})
    vehicle = (
        Vehicle.objects.select_related("seat_layout").filter(public_id=target_vehicle_id, office=context.office).first()
    )
    if vehicle is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    assert_vehicle_assignable(vehicle, service_date=trip.scheduled_departure_at.date())
    if vehicle.id == trip.vehicle_id:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "target_vehicle_id", "reason": "must_change"}])
    active_assignments = list(
        SeatAssignment.objects.select_for_update()
        .filter(trip=trip, status=SeatAssignment.Status.ACTIVE, passenger__status=BookingPassenger.Status.ACTIVE)
        .select_related("passenger__booking", "trip_seat__layout_seat")
        .order_by("passenger__booking__pnr", "passenger__sequence_no")
    )
    inputs = [AssignmentInput(item, item.passenger, item.trip_seat.layout_seat) for item in active_assignments]
    allocation, conflicts = _solve(inputs, vehicle.seat_layout_id)
    source_version = (
        TripSeat.objects.filter(trip=trip, is_current=True)
        .order_by("-inventory_version")
        .values_list("inventory_version", flat=True)
        .first()
        or 1
    )
    TripReallocationPlan.objects.filter(
        trip=trip, status__in=[TripReallocationPlan.Status.PREVIEWED, TripReallocationPlan.Status.CONFLICTED]
    ).update(status=TripReallocationPlan.Status.SUPERSEDED)
    status = TripReallocationPlan.Status.CONFLICTED if conflicts else TripReallocationPlan.Status.PREVIEWED
    plan = TripReallocationPlan.objects.create(
        trip=trip,
        previous_vehicle=trip.vehicle,
        target_vehicle=vehicle,
        previous_layout=trip.seat_layout,
        target_layout=vehicle.seat_layout,
        trip_version=trip.version,
        source_inventory_version=source_version,
        target_inventory_version=source_version + 1,
        status=status,
        conflict_count=len(conflicts),
        created_by=actor,
        simulation={"algorithm": "protected_group_gender_type_distance_v1", "passenger_count": len(inputs)},
    )
    lines: list[TripReallocationLine] = []
    for item in inputs:
        target = allocation.get(item.passenger.id)
        if target is None:
            lines.append(
                TripReallocationLine(
                    plan=plan,
                    passenger=item.passenger,
                    old_assignment=item.assignment,
                    old_seat_code=item.old_layout_seat.seat_code,
                    old_seat_type=item.old_layout_seat.seat_type,
                    status=TripReallocationLine.Status.CONFLICT,
                    conflict_code="SEAT_REALLOCATION_REQUIRED",
                )
            )
        else:
            seat, score = target
            lines.append(
                TripReallocationLine(
                    plan=plan,
                    passenger=item.passenger,
                    old_assignment=item.assignment,
                    old_seat_code=item.old_layout_seat.seat_code,
                    old_seat_type=item.old_layout_seat.seat_type,
                    target_layout_seat=seat,
                    target_seat_code=seat.seat_code,
                    target_seat_type=seat.seat_type,
                    score=score,
                )
            )
    TripReallocationLine.objects.bulk_create(lines)
    response = {"plan_id": str(plan.id)}
    _complete_idempotency(record, response)
    record_audit(
        action="office.trip.vehicle_change.preview",
        object_type="trip_reallocation_plan",
        object_id=plan.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"target_vehicle_id": vehicle.public_id, "conflict_count": plan.conflict_count},
    )
    return plan


@transaction.atomic
def apply_vehicle_reallocation(
    *, context: OfficeContext, actor: User, request: HttpRequest, trip_id: str, plan_id: str, idempotency_key: str
) -> TripReallocationPlan:
    trip = (
        Trip.objects.select_for_update()
        .select_related("vehicle", "seat_layout", "office")
        .filter(public_id=trip_id, office=context.office)
        .first()
    )
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    record, replay = _begin_idempotency(
        scope="trip_reallocation_apply", scope_id=trip.id, key=idempotency_key, payload={"plan_id": plan_id}
    )
    if replay is not None:
        return TripReallocationPlan.objects.get(id=replay["plan_id"])
    plan = (
        TripReallocationPlan.objects.select_for_update()
        .select_related("target_vehicle", "target_layout", "previous_vehicle", "previous_layout")
        .filter(id=plan_id, trip=trip)
        .first()
    )
    if plan is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if plan.status != TripReallocationPlan.Status.PREVIEWED or plan.conflict_count:
        raise DomainAPIException("SEAT_REALLOCATION_REQUIRED")
    if plan.trip_version != trip.version:
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": trip.version})
    if BookingPassenger.objects.filter(
        booking__trip=trip, boarding_status=BookingPassenger.BoardingStatus.BOARDED
    ).exists():
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    now = timezone.now()
    SeatHold.objects.filter(trip=trip, status=SeatHold.Status.ACTIVE).update(
        status=SeatHold.Status.RELEASED, released_at=now
    )
    TripSeat.objects.filter(trip=trip, is_current=True).update(
        is_current=False, sellable=False, blocked_reason=f"vehicle_change:{plan.id}"
    )
    target_layout_seats = list(plan.target_layout.seats.all())
    new_inventory = TripSeat.objects.bulk_create(
        [
            TripSeat(
                trip=trip,
                layout_seat=seat,
                seat_code=seat.seat_code,
                seat_type=seat.seat_type,
                sellable=seat.is_sellable,
                blocked_reason=None if seat.is_sellable else "layout_not_sellable",
                inventory_version=plan.target_inventory_version,
                is_current=True,
            )
            for seat in target_layout_seats
        ]
    )
    by_layout = {item.layout_seat_id: item for item in new_inventory}
    changed_bookings: set[uuid.UUID] = set()
    for line in plan.lines.select_for_update(of=("self",)).select_related(
        "passenger", "old_assignment", "target_layout_seat"
    ):
        if line.target_layout_seat_id is None:
            raise DomainAPIException("SEAT_REALLOCATION_REQUIRED")
        old = SeatAssignment.objects.select_for_update().get(id=line.old_assignment_id)
        if old.status != SeatAssignment.Status.ACTIVE:
            raise DomainAPIException("VERSION_CONFLICT")
        target_trip_seat = by_layout[line.target_layout_seat_id]
        old.status = SeatAssignment.Status.MOVED
        old.released_at = now
        old.save(update_fields=["status", "released_at"])
        replacement = SeatAssignment.objects.create(
            trip=trip,
            booking=old.booking,
            passenger=old.passenger,
            trip_seat=target_trip_seat,
            status=SeatAssignment.Status.ACTIVE,
            price_amount=old.price_amount,
        )
        old.superseded_by = replacement
        old.save(update_fields=["superseded_by"])
        line.status = TripReallocationLine.Status.APPLIED
        line.save(update_fields=["status"])
        reissue_ticket_for_passenger(
            passenger=line.passenger,
            seat_assignment=replacement,
            reason="vehicle_reallocation",
        )
        changed_bookings.add(old.booking_id)
    previous = {
        "vehicle_id": trip.vehicle.public_id,
        "seat_layout_id": str(trip.seat_layout_id),
        "version": trip.version,
    }
    trip.vehicle = plan.target_vehicle
    trip.seat_layout = plan.target_layout
    trip.version += 1
    trip.save(update_fields=["vehicle", "seat_layout", "version", "updated_at"])
    change = TripChange.objects.create(
        trip=trip,
        change_type=TripChange.ChangeType.VEHICLE,
        classification=TripChange.Classification.MATERIAL,
        previous_snapshot=previous,
        new_snapshot={
            "vehicle_id": trip.vehicle.public_id,
            "seat_layout_id": str(trip.seat_layout_id),
            "reallocation_plan_id": str(plan.id),
            "version": trip.version,
        },
        response_deadline_at=min(
            trip.scheduled_departure_at,
            now + timedelta(hours=int(getattr(settings, "TRIP_CHANGE_RESPONSE_HOURS", 24))),
        ),
        created_by=actor,
    )
    TripChangeResponse.objects.bulk_create(
        [TripChangeResponse(change=change, booking_id=booking_id) for booking_id in changed_bookings],
        ignore_conflicts=True,
    )
    plan.status = TripReallocationPlan.Status.APPLIED
    plan.applied_by = actor
    plan.applied_at = now
    plan.save(update_fields=["status", "applied_by", "applied_at"])
    OutboxEvent.objects.create(
        aggregate_type="trip_reallocation",
        aggregate_id=plan.id,
        event_type="trip.vehicle_reallocated",
        payload={
            "trip_id": trip.public_id,
            "target_vehicle_id": trip.vehicle.public_id,
            "affected_booking_ids": [str(value) for value in changed_bookings],
            "trip_change_id": str(change.id),
        },
    )
    record_audit(
        action="office.trip.vehicle_change.apply",
        object_type="trip_reallocation_plan",
        object_id=plan.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before=previous,
        after={
            "vehicle_id": trip.vehicle.public_id,
            "version": trip.version,
            "moved_passengers": len(changed_bookings),
        },
    )
    _complete_idempotency(record, {"plan_id": str(plan.id)})
    return plan


@transaction.atomic
def respond_to_trip_change(
    *, pnr: str, manage_token: str, change_id: str, choice: str, idempotency_key: str
) -> TripChangeResponse:
    booking = Booking.objects.select_for_update().filter(pnr=pnr.strip().upper()).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    record, replay = begin_idempotency(
        scope_type="trip_change_response",
        scope_id=booking.id,
        key=idempotency_key,
        payload={"change_id": change_id, "choice": choice},
    )
    if replay is not None:
        return TripChangeResponse.objects.select_related("change", "booking").get(id=replay["response_id"])
    response = (
        TripChangeResponse.objects.select_for_update()
        .select_related("change")
        .filter(change_id=uuid.UUID(change_id), booking=booking)
        .first()
    )
    if response is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if response.status != TripChangeResponse.Status.PENDING:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if choice == "accept":
        response.status = TripChangeResponse.Status.ACCEPTED
    elif choice == "alternative":
        response.status = TripChangeResponse.Status.ALTERNATIVE_REQUESTED
    elif choice == "refund":
        response.status = TripChangeResponse.Status.REFUND_REQUESTED
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    response.responded_at = timezone.now()
    response.save(update_fields=["status", "responded_at"])
    complete_idempotency(record, {"response_id": str(response.id)})
    OutboxEvent.objects.create(
        aggregate_type="trip_change_response",
        aggregate_id=response.id,
        event_type="booking.trip_change.responded",
        payload={"booking_id": booking.public_id, "change_id": str(response.change_id), "choice": choice},
    )
    return response


@transaction.atomic
def interrupt_trip(
    *, context: OfficeContext, actor: User, request: HttpRequest, trip_id: str, version: int, reason_code: str
) -> Trip:
    trip = Trip.objects.select_for_update().filter(public_id=trip_id, office=context.office).first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if trip.version != version:
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": trip.version})
    if trip.status != Trip.Status.DEPARTED:
        raise DomainAPIException("TRIP_NOT_DEPARTED")
    if not reason_code.strip():
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "reason_code", "reason": "required"}])
    trip.status = Trip.Status.INTERRUPTED
    trip.version += 1
    trip.save(update_fields=["status", "version", "updated_at"])
    bookings = Booking.objects.filter(
        trip=trip, status__in=[Booking.Status.CONFIRMED, Booking.Status.DENIED_BOARDING_REVIEW]
    )
    TripInterruptionResolution.objects.bulk_create(
        [TripInterruptionResolution(trip=trip, booking=booking) for booking in bookings], ignore_conflicts=True
    )
    TripOperationalIssue.objects.create(
        trip=trip,
        issue_type=TripOperationalIssue.IssueType.URGENT_CASE,
        details={"reason_code": reason_code, "incident": "trip_interrupted"},
    )
    OutboxEvent.objects.create(
        aggregate_type="trip",
        aggregate_id=trip.id,
        event_type="trip.interrupted",
        payload={"trip_id": trip.public_id, "reason_code": reason_code, "affected_bookings": bookings.count()},
    )
    record_audit(
        action="office.trip.interrupt",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"status": trip.status, "version": trip.version, "reason_code": reason_code},
        reason_code=reason_code,
    )
    return trip


@transaction.atomic
def resolve_interruption_booking(
    *,
    actor: User,
    request: HttpRequest,
    trip_id: str,
    booking_id: str,
    resolution: str,
    details: dict[str, Any],
    idempotency_key: str,
) -> TripInterruptionResolution:
    trip = Trip.objects.select_for_update().filter(public_id=trip_id).first()
    if trip is None or trip.status != Trip.Status.INTERRUPTED:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    idempotency, replay = begin_idempotency(
        scope_type="trip_interruption_booking",
        scope_id=trip.id,
        key=idempotency_key,
        payload={"booking_id": booking_id, "resolution": resolution, "details": details},
    )
    if replay is not None:
        return TripInterruptionResolution.objects.select_related("booking").get(id=replay["resolution_id"])
    record = (
        TripInterruptionResolution.objects.select_for_update().filter(trip=trip, booking__public_id=booking_id).first()
    )
    if record is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    allowed = {
        choice
        for choice, _ in TripInterruptionResolution.Status.choices
        if choice != TripInterruptionResolution.Status.PENDING
    }
    if resolution not in allowed:
        raise DomainAPIException("VALIDATION_ERROR")
    record.status = resolution
    record.resolution_details = details
    record.resolved_by = actor
    record.resolved_at = timezone.now()
    record.save(update_fields=["status", "resolution_details", "resolved_by", "resolved_at"])
    complete_idempotency(idempotency, {"resolution_id": str(record.id)})
    record_audit(
        action="platform.trip.interruption.resolve_booking",
        object_type="trip_interruption_resolution",
        object_id=record.id,
        actor_user=actor,
        office_id=trip.office_id,
        request=request,
        after={"status": record.status, "details": details},
    )
    return record


@transaction.atomic
def close_interrupted_trip(
    *, actor: User, request: HttpRequest, trip_id: str, outcome: str, version: int, idempotency_key: str
) -> Trip:
    trip = Trip.objects.select_for_update().filter(public_id=trip_id).first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    idempotency, replay = begin_idempotency(
        scope_type="trip_interruption_close",
        scope_id=trip.id,
        key=idempotency_key,
        payload={"outcome": outcome, "version": version},
    )
    if replay is not None:
        return Trip.objects.get(id=replay["trip_id"])
    if trip.version != version:
        raise DomainAPIException("VERSION_CONFLICT", details={"current_version": trip.version})
    if trip.status != Trip.Status.INTERRUPTED:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    unresolved = trip.interruption_resolutions.filter(status=TripInterruptionResolution.Status.PENDING)
    if unresolved.exists():
        raise DomainAPIException("INCIDENT_NOT_RESOLVED", details={"pending_count": unresolved.count()})
    if outcome == "completed":
        trip.status = Trip.Status.COMPLETED
    elif outcome == "cancelled":
        trip.status = Trip.Status.CANCELLED
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    trip.version += 1
    trip.save(update_fields=["status", "version", "updated_at"])
    complete_idempotency(idempotency, {"trip_id": str(trip.id)})
    TripOperationalIssue.objects.filter(
        trip=trip, status=TripOperationalIssue.Status.OPEN, details__incident="trip_interrupted"
    ).update(status=TripOperationalIssue.Status.RESOLVED, resolved_at=timezone.now())
    OutboxEvent.objects.create(
        aggregate_type="trip",
        aggregate_id=trip.id,
        event_type=f"trip.interrupted_resolved_{outcome}",
        payload={"trip_id": trip.public_id, "outcome": outcome},
    )
    record_audit(
        action=f"platform.trip.interruption.close_{outcome}",
        object_type="trip",
        object_id=trip.id,
        actor_user=actor,
        office_id=trip.office_id,
        request=request,
        after={"status": trip.status, "version": trip.version},
    )
    return trip
