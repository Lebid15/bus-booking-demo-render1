from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from bookings.models import Booking, BookingPassenger, SeatAssignment
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from fleet.models import Driver, SeatLayout, SeatLayoutSeat, Vehicle
from geography.models import Location, Route
from identity.models import Role, User
from organizations.models import Office, OfficeBranch, OfficeMembership, TransportOperator
from organizations.services import OfficeContext
from policies.models import PolicyTemplate, PolicyVersion
from trips.models import Trip, TripCancellationAction, TripChange, TripChangeResponse, TripSeat
from trips.services import (
    command_trip,
    create_trip,
    open_due_trip_bookings,
    update_trip,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def request_for(user: User):  # type: ignore[no-untyped-def]
    request = RequestFactory().post("/v1/office/trips", HTTP_IDEMPOTENCY_KEY="trip-test-key")
    request.user = user
    return request


def environment(*, base_price: str = "150000") -> tuple[User, OfficeContext, dict[str, object]]:
    user = User.objects.create_user(
        full_name="مدير الرحلات",
        email=f"trips-{uuid.uuid4()}@example.com",
        password="SecurePass!234",
    )
    operator = TransportOperator.objects.create(
        legal_name="الناقل السوري",
        trade_name="الناقل",
        status="active",
    )
    office = Office.objects.create(
        operator=operator,
        legal_name="مكتب رحلات الرقة",
        trade_name="رحلات الرقة",
        office_type=Office.OfficeType.CARRIER,
        status=Office.Status.ACTIVE,
        support_phone="+963900000000",
    )
    role = Role.objects.create(
        code=f"office.trip.owner.{uuid.uuid4()}",
        scope_type=Role.ScopeType.OFFICE,
        name_ar="مدير الرحلات",
    )
    membership = OfficeMembership.objects.create(user=user, office=office, role=role)
    context = OfficeContext(membership=membership, permissions=frozenset({"office.trip.manage"}))

    raqqa = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="الرقة")
    damascus = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="دمشق")
    garage = Location.objects.create(
        location_type=Location.LocationType.GARAGE,
        parent=raqqa,
        name_ar="كراج الرقة",
    )
    branch = OfficeBranch.objects.create(
        office=office,
        name="الفرع الرئيسي",
        location=garage,
        status="active",
        is_primary=True,
    )
    route = Route.objects.create(
        origin_location=raqqa,
        destination_location=damascus,
        name_ar="الرقة - دمشق",
        status=Route.Status.ACTIVE,
    )
    layout = SeatLayout.objects.create(
        office=office,
        name="بولمان 2+2",
        layout_type=SeatLayout.LayoutType.TWO_PLUS_TWO,
        seat_count=2,
        status=SeatLayout.Status.ACTIVE,
    )
    SeatLayoutSeat.objects.create(
        layout=layout,
        seat_code="1A",
        row_no=1,
        column_no=1,
        seat_type=SeatLayoutSeat.SeatType.STANDARD,
    )
    SeatLayoutSeat.objects.create(
        layout=layout,
        seat_code="1B",
        row_no=1,
        column_no=2,
        seat_type=SeatLayoutSeat.SeatType.STANDARD,
    )
    vehicle = Vehicle.objects.create(
        office=office,
        operator=operator,
        plate_number=f"RAQ-{uuid.uuid4().hex[:6]}",
        seat_layout=layout,
        status=Vehicle.Status.ACTIVE,
    )
    driver = Driver.objects.create(
        operator=operator,
        full_name="سائق الرحلة",
        license_number_ciphertext=b"encrypted",
        license_last4="1234",
        license_expires_at=timezone.localdate() + timedelta(days=180),
        status=Driver.Status.ACTIVE,
    )
    now = timezone.now()
    data: dict[str, object] = {
        "route_id": route.public_id,
        "branch_id": branch.public_id,
        "operator_id": operator.public_id,
        "vehicle_id": vehicle.public_id,
        "driver_id": driver.public_id,
        "scheduled_departure_at": now + timedelta(days=2),
        "scheduled_arrival_at": now + timedelta(days=2, hours=8),
        "currency": "SYP",
        "base_price": Decimal(base_price),
        "payment_methods": ["office_cash", "manual_transfer"],
        "booking_open_at": now - timedelta(minutes=5),
        "booking_close_at": now + timedelta(days=1, hours=20),
        "boarding_open_at": now + timedelta(days=1, hours=22),
        "boarding_close_at": now + timedelta(days=1, hours=23, minutes=30),
    }
    return user, context, data


def seed_required_policies(*, office: Office | None = None) -> list[PolicyVersion]:
    now = timezone.now()
    versions: list[PolicyVersion] = []
    for policy_type in ("cancellation", "payment", "boarding"):
        template = PolicyTemplate.objects.create(
            code=f"{policy_type}.standard.{uuid.uuid4().hex[:6]}",
            policy_type=policy_type,
            owner_scope=PolicyTemplate.OwnerScope.OFFICE if office else PolicyTemplate.OwnerScope.PLATFORM,
            status=PolicyTemplate.Status.ACTIVE,
        )
        content = f"سياسة {policy_type}"
        versions.append(
            PolicyVersion.objects.create(
                template=template,
                office=office,
                version_no=1,
                language="ar",
                title=content,
                content_markdown=content,
                rules_json={"summary": content},
                effective_from=now - timedelta(days=1),
                published_at=now - timedelta(days=1),
                content_sha256=hashlib.sha256(content.encode()).hexdigest(),
            )
        )
    return versions


def create_valid_trip() -> tuple[User, OfficeContext, Trip]:
    user, context, data = environment()
    policies = seed_required_policies()
    data["policy_version_ids"] = [policy.id for policy in policies]
    trip = create_trip(
        context=context,
        actor=user,
        request=request_for(user),
        data=data,
    )
    return user, context, trip


def schedule_and_publish(user: User, context: OfficeContext, trip: Trip) -> Trip:
    trip = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "schedule", "version": trip.version},
    )
    trip = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "publish", "version": trip.version},
    )
    return trip


def booking_for(trip: Trip, *, status: str = Booking.Status.CONFIRMED) -> Booking:
    return Booking.objects.create(
        office=trip.office,
        branch=trip.branch,
        trip=trip,
        source=Booking.Source.PUBLIC_WEB,
        status=status,
        payment_status=Booking.PaymentStatus.PAID,
        contact_name="راكب تجريبي",
        contact_phone="+963944000000",
        currency=trip.currency,
        subtotal_amount=trip.base_price,
        total_amount=trip.base_price,
        paid_amount=trip.base_price,
        policy_snapshot=trip.policy_snapshot,
        pricing_snapshot=trip.pricing_snapshot,
        commission_snapshot={},
        terms_version_ids=[],
        manage_token_hash=uuid.uuid4().bytes,
        confirmed_at=timezone.now(),
    )


@override_settings(TRIP_REQUIRED_POLICY_TYPES="cancellation,payment,boarding")
def test_e04_ac01_schedule_returns_missing_fields_and_does_not_mutate_trip() -> None:
    user, context, data = environment(base_price="0")
    trip = create_trip(context=context, actor=user, request=request_for(user), data=data)

    with pytest.raises(DomainAPIException) as exc:
        command_trip(
            context=context,
            actor=user,
            request=request_for(user),
            trip_id=trip.public_id,
            data={"command": "schedule", "version": trip.version},
        )

    assert exc.value.code == "TRIP_NOT_READY"
    assert isinstance(exc.value.details, dict)
    assert "base_price" in exc.value.details["missing_fields"]
    assert "policy:cancellation" in exc.value.details["missing_fields"]
    trip.refresh_from_db()
    assert trip.status == Trip.Status.DRAFT
    assert trip.seats.count() == 0


def test_schedule_captures_policy_pricing_stops_and_seat_inventory_snapshots() -> None:
    user, context, trip = create_valid_trip()
    scheduled = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "schedule", "version": trip.version},
    )

    assert scheduled.status == Trip.Status.SCHEDULED
    assert scheduled.seats.count() == scheduled.seat_layout.seat_count == 2
    assert scheduled.stops.count() == 2
    assert set(scheduled.policy_snapshot) == {"cancellation", "payment", "boarding"}
    assert scheduled.pricing_snapshot["base_price"] == "150000.00"
    assert scheduled.pricing_snapshot["payment_methods"] == ["office_cash", "manual_transfer"]
    assert OutboxEvent.objects.filter(aggregate_id=trip.id, event_type="trip.scheduled").count() == 1


@pytest.mark.django_db(transaction=True)
def test_e04_ac02_booking_opens_automatically_once() -> None:
    user, context, trip = create_valid_trip()
    trip = schedule_and_publish(user, context, trip)

    assert open_due_trip_bookings(now=timezone.now()) == 1
    assert open_due_trip_bookings(now=timezone.now()) == 0
    trip.refresh_from_db()
    assert trip.status == Trip.Status.BOOKING_OPEN
    assert OutboxEvent.objects.filter(
        aggregate_id=trip.id,
        event_type="trip.booking_opened",
    ).count() == 1


def test_e04_ac03_material_time_change_creates_explicit_customer_responses() -> None:
    user, context, trip = create_valid_trip()
    trip = schedule_and_publish(user, context, trip)
    trip = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "open_booking", "version": trip.version},
    )
    booking = booking_for(trip)
    new_departure = trip.scheduled_departure_at + timedelta(hours=2)

    updated = update_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"scheduled_departure_at": new_departure, "version": trip.version},
    )

    change = TripChange.objects.get(trip=trip)
    response = TripChangeResponse.objects.get(change=change, booking=booking)
    assert updated.scheduled_departure_at == new_departure
    assert change.classification == TripChange.Classification.MATERIAL
    assert response.status == TripChangeResponse.Status.PENDING
    assert OutboxEvent.objects.filter(
        aggregate_type="trip_change",
        event_type="notification.requested",
    ).count() == 1


def test_e04_ac04_departure_is_blocked_for_confirmed_passenger_without_seat() -> None:
    user, context, trip = create_valid_trip()
    trip = schedule_and_publish(user, context, trip)
    trip.status = Trip.Status.BOARDING_CLOSED
    trip.save(update_fields=["status"])
    booking = booking_for(trip)
    passenger = BookingPassenger.objects.create(
        booking=booking,
        sequence_no=1,
        full_name="محمد الراكب",
        gender=BookingPassenger.Gender.MALE,
    )

    with pytest.raises(DomainAPIException) as exc:
        command_trip(
            context=context,
            actor=user,
            request=request_for(user),
            trip_id=trip.public_id,
            data={"command": "depart", "version": trip.version},
        )
    assert exc.value.code == "TRIP_DEPARTURE_BLOCKED"
    assert isinstance(exc.value.details, dict)
    blockers = exc.value.details["blockers"]
    assert isinstance(blockers, list)
    assert {item["type"] for item in blockers} >= {"passenger_without_seat"}

    seat = TripSeat.objects.filter(trip=trip, sellable=True).first()
    assert seat is not None
    SeatAssignment.objects.create(
        trip=trip,
        booking=booking,
        passenger=passenger,
        trip_seat=seat,
        price_amount=trip.base_price,
    )
    departed = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "depart", "version": trip.version},
    )
    assert departed.status == Trip.Status.DEPARTED
    assert departed.actual_departure_at is not None


def test_e04_ac05_cancellation_stops_sales_and_starts_action_for_every_booking() -> None:
    user, context, trip = create_valid_trip()
    trip = schedule_and_publish(user, context, trip)
    trip = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "open_booking", "version": trip.version},
    )
    first = booking_for(trip)
    second = booking_for(trip)

    cancelled = command_trip(
        context=context,
        actor=user,
        request=request_for(user),
        trip_id=trip.public_id,
        data={"command": "cancel", "reason_code": "vehicle_breakdown", "version": trip.version},
    )

    assert cancelled.status == Trip.Status.CANCELLED
    assert not TripSeat.objects.filter(trip=trip, sellable=True).exists()
    assert TripCancellationAction.objects.filter(trip=trip).count() == 2
    assert Booking.objects.filter(id__in=[first.id, second.id], status=Booking.Status.CANCELLATION_PENDING).count() == 2
    assert OutboxEvent.objects.filter(
        aggregate_id=trip.id,
        event_type="trip.cancellation_action_required",
    ).count() == 2
