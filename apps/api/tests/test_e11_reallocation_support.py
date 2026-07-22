from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from boarding.services import execute_boarding_command
from bookings.models import SeatAssignment
from bookings.services import create_public_booking, get_public_booking
from common.exceptions import DomainAPIException
from fleet.models import SeatAdjacency, SeatLayout, SeatLayoutSeat, Vehicle
from identity.models import User
from organizations.services import OfficeContext
from support.models import OfficeViolation, SupportCase
from support.services import escalate_overdue_support_cases, open_guest_support_case, recovery_lookup
from tickets.models import Ticket
from trips.models import Trip, TripInterruptionResolution, TripSeat
from trips.reallocation_services import (
    apply_vehicle_reallocation,
    close_interrupted_trip,
    preview_vehicle_reallocation,
    resolve_interruption_booking,
    respond_to_trip_change,
)
from trips.services import command_trip

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import _add_same_unit_adjacency, _booking_payload, _hold
from .test_e08_tickets_self_service import _confirmed_booking
from .test_e10_boarding_offline import _environment

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _office_context(trip: Trip) -> tuple[User, OfficeContext]:
    actor = trip.created_by
    membership = actor.office_memberships.get(office=trip.office)
    return actor, OfficeContext(
        membership=membership,
        permissions=frozenset({"office.trip.manage", "office.boarding.scan", "office.support.manage"}),
    )


def _post(user: User, key: str):  # type: ignore[no-untyped-def]
    request = RequestFactory().post(
        "/v1/office/e11",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="203.0.113.111",
    )
    request.user = user
    return request


def _target_vehicle(trip: Trip) -> Vehicle:
    layout = SeatLayout.objects.create(
        office=trip.office,
        name=f"بديل-{uuid.uuid4().hex[:6]}",
        layout_type=SeatLayout.LayoutType.TWO_PLUS_TWO,
        seat_count=4,
        version=1,
        status=SeatLayout.Status.ACTIVE,
    )
    seats: dict[str, SeatLayoutSeat] = {}
    for column, code in enumerate(("N1", "N2", "N3", "N4"), start=1):
        seats[code] = SeatLayoutSeat.objects.create(
            layout=layout,
            seat_code=code,
            row_no=1 if column <= 2 else 2,
            column_no=column if column <= 2 else column - 2,
            seat_type=SeatLayoutSeat.SeatType.STANDARD,
        )
    for left, right in (("N1", "N2"), ("N3", "N4")):
        first, second = sorted((seats[left], seats[right]), key=lambda item: item.id)
        SeatAdjacency.objects.create(
            layout=layout,
            seat_a=first,
            seat_b=second,
            adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
        )
    return Vehicle.objects.create(
        office=trip.office,
        operator=trip.operator,
        plate_number=f"ALT-{uuid.uuid4().hex[:8]}",
        seat_layout=layout,
        status=Vehicle.Status.ACTIVE,
    )


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e11_ac01_vehicle_reallocation_preserves_groups_gender_and_unique_seats() -> None:
    trip = _bookable_trip()
    _add_same_unit_adjacency(trip)
    old_seats = list(trip.seats.filter(is_current=True).order_by("seat_code"))
    family_hold, family_passengers = _hold(
        trip,
        seats=old_seats[:2],
        genders=["female", "female"],
        passenger_types=["adult", "child"],
        key="e11-family-hold",
    )
    family_created = create_public_booking(
        payload=_booking_payload(trip, family_hold, family_passengers),
        idempotency_key="e11-family-booking",
        request=_request(key="e11-family-booking"),
    )
    male_hold, male_passengers = _hold(
        trip,
        seats=[old_seats[2]],
        genders=["male"],
        key="e11-male-hold",
    )
    create_public_booking(
        payload=_booking_payload(trip, male_hold, male_passengers),
        idempotency_key="e11-male-booking",
        request=_request(key="e11-male-booking"),
    )
    actor, context = _office_context(trip)
    target = _target_vehicle(trip)
    plan = preview_vehicle_reallocation(
        context=context,
        actor=actor,
        request=_post(actor, "e11-preview-plan"),
        trip_id=trip.public_id,
        target_vehicle_id=target.public_id,
        version=trip.version,
        idempotency_key="e11-preview-plan",
    )
    assert plan.conflict_count == 0
    applied = apply_vehicle_reallocation(
        context=context,
        actor=actor,
        request=_post(actor, "e11-apply-plan"),
        trip_id=trip.public_id,
        plan_id=str(plan.id),
        idempotency_key="e11-apply-plan",
    )
    assert applied.status == "applied"
    trip.refresh_from_db()
    assert trip.vehicle == target
    assert TripSeat.objects.filter(trip=trip, is_current=True).count() == 4
    active = list(
        SeatAssignment.objects.filter(trip=trip, status=SeatAssignment.Status.ACTIVE)
        .select_related("passenger__booking", "trip_seat__layout_seat")
        .order_by("passenger__booking__pnr", "passenger__sequence_no")
    )
    assert len(active) == 3
    assert len({item.trip_seat_id for item in active}) == 3
    family = [item for item in active if item.booking.public_id == family_created["id"]]
    assert len(family) == 2
    pair = SeatAdjacency.objects.filter(
        layout=target.seat_layout,
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
        seat_a_id__in=[family[0].trip_seat.layout_seat_id, family[1].trip_seat.layout_seat_id],
        seat_b_id__in=[family[0].trip_seat.layout_seat_id, family[1].trip_seat.layout_seat_id],
    )
    assert pair.exists()
    assert Ticket.objects.filter(booking__trip=trip, status=Ticket.Status.ACTIVE, version_no=2).count() == 3
    managed = get_public_booking(
        pnr=str(family_created["pnr"]),
        manage_token=str(family_created["manage_token"]),
    )
    assert managed["trip_changes"][0]["status"] == "pending"
    assert "respond_trip_change" in managed["manage_actions"]
    response = respond_to_trip_change(
        pnr=str(family_created["pnr"]),
        manage_token=str(family_created["manage_token"]),
        change_id=str(managed["trip_changes"][0]["change_id"]),
        choice="accept",
        idempotency_key="e11-family-change-response",
    )
    replay = respond_to_trip_change(
        pnr=str(family_created["pnr"]),
        manage_token=str(family_created["manage_token"]),
        change_id=str(managed["trip_changes"][0]["change_id"]),
        choice="accept",
        idempotency_key="e11-family-change-response",
    )
    assert replay.id == response.id
    assert response.status == "accepted"


def test_e11_ac02_valid_ticket_denial_opens_p1_freezes_seat_and_escalates() -> None:
    booking, _, actor, context, session = _environment()
    passenger = booking.passengers.get()
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_post(actor, "e11-arrive"),
        trip_id=booking.trip.public_id,
        data={"command": "arrive", "passenger_id": passenger.id},
        idempotency_key="e11-arrive",
    )
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_post(actor, "e11-deny"),
        trip_id=booking.trip.public_id,
        data={"command": "deny", "passenger_id": passenger.id, "reason_code": "office_rejected_valid_ticket"},
        idempotency_key="e11-deny",
    )
    case = SupportCase.objects.get(booking=booking, category="boarding_denial_valid_ticket")
    assignment = SeatAssignment.objects.get(passenger=passenger, status=SeatAssignment.Status.ACTIVE)
    assignment.trip_seat.refresh_from_db()
    assert case.priority == SupportCase.Priority.P1
    assert case.status == SupportCase.Status.ESCALATED
    assert assignment.trip_seat.sellable is False
    assert case.public_id in str(assignment.trip_seat.blocked_reason)
    assert case.metadata["auto_escalated"] is True


@override_settings(SUPPORT_P1_SLA_MINUTES=1)
def test_e11_ac03_overdue_office_case_escalates_to_platform_and_records_violation() -> None:
    booking, created = _confirmed_booking()
    case = open_guest_support_case(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        data={
            "category": "office_not_responding",
            "priority": "P1",
            "message": "المكتب لا يجيب قبل موعد الرحلة",
            "attachments": [],
        },
        request=None,
        idempotency_key="e11-office-no-response",
    )
    replay = open_guest_support_case(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        data={
            "category": "office_not_responding",
            "priority": "P1",
            "message": "المكتب لا يجيب قبل موعد الرحلة",
            "attachments": [],
        },
        request=None,
        idempotency_key="e11-office-no-response",
    )
    assert replay.id == case.id
    SupportCase.objects.filter(id=case.id).update(sla_due_at=timezone.now() - timedelta(seconds=1))
    assert escalate_overdue_support_cases() == 1
    case.refresh_from_db()
    assert case.status == SupportCase.Status.ESCALATED
    assert OfficeViolation.objects.filter(
        support_case=case, code="SUPPORT_SLA_BREACH", status=OfficeViolation.Status.OPEN
    ).exists()


def test_e11_ac04_outage_recovery_uses_manifest_or_pnr_without_new_payment() -> None:
    booking, _ = _confirmed_booking()
    actor, context = _office_context(booking.trip)
    before_paid = booking.paid_amount
    result = recovery_lookup(
        context=context,
        trip_id=booking.trip.public_id,
        pnr=booking.pnr,
        identity_tail=None,
    )
    booking.refresh_from_db()
    assert result["pnr"] == booking.pnr
    assert result["payment_required"] is False
    assert result["verification_source"] == "manifest_pnr_recovery"
    assert result["passengers"][0]["ticket_status"] == Ticket.Status.ACTIVE
    assert booking.paid_amount == before_paid
    assert actor == booking.trip.created_by


def test_e11_ac05_interrupted_trip_cannot_complete_before_all_rights_are_resolved() -> None:
    booking, _, actor, context, _ = _environment()
    trip = command_trip(
        context=context,
        actor=actor,
        request=_post(actor, "e11-close-boarding"),
        trip_id=booking.trip.public_id,
        data={"command": "close_boarding", "version": booking.trip.version},
    )
    trip = command_trip(
        context=context,
        actor=actor,
        request=_post(actor, "e11-depart"),
        trip_id=trip.public_id,
        data={"command": "depart", "version": trip.version},
    )
    trip = command_trip(
        context=context,
        actor=actor,
        request=_post(actor, "e11-interrupt"),
        trip_id=trip.public_id,
        data={"command": "interrupt", "version": trip.version, "reason_code": "vehicle_breakdown"},
    )
    platform = User.objects.create_user(
        full_name="مشغل المنصة",
        email=f"platform-{uuid.uuid4()}@example.com",
        password="SecurePass!234",
        is_platform_staff=True,
    )
    with pytest.raises(DomainAPIException) as exc:
        close_interrupted_trip(
            actor=platform,
            request=_post(platform, "e11-close-too-early"),
            trip_id=trip.public_id,
            outcome="completed",
            version=trip.version,
            idempotency_key="e11-close-too-early",
        )
    assert exc.value.code == "INCIDENT_NOT_RESOLVED"
    resolution = resolve_interruption_booking(
        actor=platform,
        request=_post(platform, "e11-resolve-booking"),
        trip_id=trip.public_id,
        booking_id=booking.public_id,
        resolution=TripInterruptionResolution.Status.ALTERNATIVE_ACCEPTED,
        details={"alternative_trip": "documented"},
        idempotency_key="e11-resolve-booking",
    )
    assert resolution.status == TripInterruptionResolution.Status.ALTERNATIVE_ACCEPTED
    resolution_replay = resolve_interruption_booking(
        actor=platform,
        request=_post(platform, "e11-resolve-booking"),
        trip_id=trip.public_id,
        booking_id=booking.public_id,
        resolution=TripInterruptionResolution.Status.ALTERNATIVE_ACCEPTED,
        details={"alternative_trip": "documented"},
        idempotency_key="e11-resolve-booking",
    )
    assert resolution_replay.id == resolution.id
    closed = close_interrupted_trip(
        actor=platform,
        request=_post(platform, "e11-close-after-rights"),
        trip_id=trip.public_id,
        outcome="completed",
        version=trip.version,
        idempotency_key="e11-close-after-rights",
    )
    assert closed.status == Trip.Status.COMPLETED
    closed_replay = close_interrupted_trip(
        actor=platform,
        request=_post(platform, "e11-close-after-rights"),
        trip_id=trip.public_id,
        outcome="completed",
        version=trip.version,
        idempotency_key="e11-close-after-rights",
    )
    assert closed_replay.id == closed.id
