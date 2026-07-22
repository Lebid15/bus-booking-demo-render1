from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import create_public_seat_hold, expire_due_holds, release_public_seat_hold
from common.exceptions import DomainAPIException
from fleet.models import Driver, SeatLayout, SeatLayoutSeat, Vehicle
from geography.models import Location, Route
from identity.models import Role, User
from organizations.models import Office, OfficeBranch, OfficeMembership, TransportOperator
from organizations.services import OfficeContext
from policies.models import PolicyTemplate, PolicyVersion
from trips.models import SeatHold, Trip
from trips.public_services import public_seat_map, search_public_trips
from trips.services import command_trip, create_trip

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _request(user: User | None = None, *, key: str = "public-hold-test"):
    request = RequestFactory().post(
        "/v1/public/trips/test/seat-holds",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="203.0.113.10",
    )
    request.user = user
    return request


def _seed_policies() -> list[PolicyVersion]:
    now = timezone.now()
    versions: list[PolicyVersion] = []
    for policy_type in ("cancellation", "payment", "boarding"):
        template = PolicyTemplate.objects.create(
            code=f"{policy_type}.{uuid.uuid4().hex[:8]}",
            policy_type=policy_type,
            owner_scope=PolicyTemplate.OwnerScope.PLATFORM,
            status=PolicyTemplate.Status.ACTIVE,
        )
        title = f"سياسة {policy_type}"
        versions.append(
            PolicyVersion.objects.create(
                template=template,
                version_no=1,
                language="ar",
                title=title,
                content_markdown=title,
                rules_json={"summary": title, "payment_deadline_minutes": 20},
                effective_from=now - timedelta(days=1),
                published_at=now - timedelta(days=1),
                content_sha256=hashlib.sha256(title.encode()).hexdigest(),
            )
        )
    return versions


def _bookable_trip(*, office_status: str = Office.Status.ACTIVE) -> Trip:
    user = User.objects.create_user(
        full_name="مدير الرحلة",
        email=f"e05-{uuid.uuid4()}@example.com",
        password="SecurePass!234",
    )
    operator = TransportOperator.objects.create(
        legal_name="ناقل الاختبار",
        trade_name="الناقل",
        status="active",
    )
    office = Office.objects.create(
        operator=operator,
        legal_name="مكتب الاختبار",
        trade_name="مكتب الاختبار",
        office_type=Office.OfficeType.CARRIER,
        status=Office.Status.ACTIVE,
        timezone="Asia/Damascus",
        support_phone="+963900000000",
    )
    role = Role.objects.create(
        code=f"trip.owner.{uuid.uuid4()}",
        scope_type=Role.ScopeType.OFFICE,
        name_ar="مدير",
    )
    membership = OfficeMembership.objects.create(user=user, office=office, role=role)
    context = OfficeContext(membership=membership, permissions=frozenset({"office.trip.manage"}))
    origin = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="الرقة")
    destination = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="دمشق")
    garage = Location.objects.create(
        location_type=Location.LocationType.GARAGE,
        parent=origin,
        name_ar="كراج الرقة",
    )
    branch = OfficeBranch.objects.create(
        office=office,
        name="الرئيسي",
        location=garage,
        is_primary=True,
    )
    route = Route.objects.create(
        origin_location=origin,
        destination_location=destination,
        name_ar="الرقة - دمشق",
    )
    layout = SeatLayout.objects.create(
        office=office,
        name="2+1",
        layout_type=SeatLayout.LayoutType.TWO_PLUS_ONE,
        seat_count=3,
        status=SeatLayout.Status.ACTIVE,
    )
    for column, code in enumerate(("1A", "1B", "1C"), start=1):
        SeatLayoutSeat.objects.create(
            layout=layout,
            seat_code=code,
            row_no=1,
            column_no=column,
        )
    vehicle = Vehicle.objects.create(
        office=office,
        operator=operator,
        plate_number=f"E05-{uuid.uuid4().hex[:6]}",
        seat_layout=layout,
        status=Vehicle.Status.ACTIVE,
    )
    driver = Driver.objects.create(
        operator=operator,
        full_name="السائق",
        license_number_ciphertext=b"encrypted",
        license_expires_at=timezone.localdate() + timedelta(days=200),
        status=Driver.Status.ACTIVE,
    )
    now = timezone.now()
    departure = now + timedelta(days=2)
    policies = _seed_policies()
    trip = create_trip(
        context=context,
        actor=user,
        request=_request(user),
        data={
            "route_id": route.public_id,
            "branch_id": branch.public_id,
            "operator_id": operator.public_id,
            "vehicle_id": vehicle.public_id,
            "driver_id": driver.public_id,
            "scheduled_departure_at": departure,
            "scheduled_arrival_at": departure + timedelta(hours=8),
            "currency": "SYP",
            "base_price": Decimal("100000"),
            "policy_version_ids": [policy.id for policy in policies],
            "payment_methods": ["office_cash", "manual_transfer"],
            "booking_open_at": now - timedelta(minutes=5),
            "booking_close_at": departure - timedelta(hours=2),
            "boarding_open_at": departure - timedelta(hours=1),
            "boarding_close_at": departure - timedelta(minutes=15),
        },
    )
    trip = command_trip(
        context=context,
        actor=user,
        request=_request(user),
        trip_id=trip.public_id,
        data={"command": "schedule", "version": trip.version},
    )
    trip.pricing_snapshot = {
        **trip.pricing_snapshot,
        "fee_per_passenger": "5000.00",
        "fixed_fee": "1000.00",
    }
    trip.save(update_fields=["pricing_snapshot"])
    trip = command_trip(
        context=context,
        actor=user,
        request=_request(user),
        trip_id=trip.public_id,
        data={"command": "publish", "version": trip.version},
    )
    trip = command_trip(
        context=context,
        actor=user,
        request=_request(user),
        trip_id=trip.public_id,
        data={"command": "open_booking", "version": trip.version},
    )
    if office_status != Office.Status.ACTIVE:
        office.status = office_status
        office.save(update_fields=["status"])
    return (
        Trip.objects.select_related(
            "office", "operator", "route__origin_location", "route__destination_location", "seat_layout"
        )
        .prefetch_related("seats__layout_seat")
        .get(id=trip.id)
    )


def _payload(trip: Trip, seat_ids: list[uuid.UUID]) -> dict[str, object]:
    return {
        "seat_ids": seat_ids,
        "passengers": [
            {"full_name": f"راكب {index}", "gender": "male", "passenger_type": "adult", "seat_id": seat_id}
            for index, seat_id in enumerate(seat_ids, start=1)
        ],
        "quote_version": trip.version,
    }


def test_e05_ac01_search_uses_office_local_date_and_only_bookable_trips() -> None:
    trip = _bookable_trip()
    local_date = trip.scheduled_departure_at.astimezone(timezone.get_fixed_timezone(180)).date()
    results = search_public_trips(
        origin_id=trip.route.origin_location.public_id,
        destination_id=trip.route.destination_location.public_id,
        service_date_raw=local_date.isoformat(),
        passengers_raw=2,
    )
    assert [result["id"] for result in results] == [trip.public_id]


def test_e05_ac02_search_discloses_honest_price_fees_and_policy() -> None:
    trip = _bookable_trip()
    local_date = trip.scheduled_departure_at.astimezone(timezone.get_fixed_timezone(180)).date()
    [result] = search_public_trips(
        origin_id=trip.route.origin_location.public_id,
        destination_id=trip.route.destination_location.public_id,
        service_date_raw=local_date.isoformat(),
        passengers_raw=1,
    )
    assert result["from_price"] == "106000.00"
    assert result["currency"] == "SYP"
    assert result["payment_methods"] == ["office_cash", "manual_transfer"]
    assert "سياسة" in str(result["cancellation_summary"])


@pytest.mark.parametrize("status", [Office.Status.NO_NEW_BOOKINGS, Office.Status.RESTRICTED, Office.Status.SUSPENDED])
def test_e05_ac05_restricted_office_trips_are_hidden(status: str) -> None:
    trip = _bookable_trip(office_status=status)
    local_date = trip.scheduled_departure_at.astimezone(timezone.get_fixed_timezone(180)).date()
    assert (
        search_public_trips(
            origin_id=trip.route.origin_location.public_id,
            destination_id=trip.route.destination_location.public_id,
            service_date_raw=local_date.isoformat(),
            passengers_raw=1,
        )
        == []
    )


@override_settings(SEAT_HOLD_TTL_SECONDS=600, PUBLIC_HOLD_RATE_LIMIT=50)
def test_public_hold_revalidates_inventory_and_is_idempotent() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    payload = _payload(trip, [seat.id])
    first = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=payload,
        idempotency_key="same-hold-key",
        request=_request(key="same-hold-key"),
    )
    second = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=payload,
        idempotency_key="same-hold-key",
        request=_request(key="same-hold-key"),
    )
    assert first["hold_token"] == second["hold_token"]
    assert SeatHold.objects.filter(trip=trip, status=SeatHold.Status.ACTIVE).count() == 1
    statuses = {item["id"]: item["status"] for item in public_seat_map(trip, hold_token=first["hold_token"])["seats"]}
    assert statuses[str(seat.id)] == "held_by_you"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=1, PUBLIC_HOLD_RATE_WINDOW_SECONDS=60)
def test_idempotent_hold_replay_does_not_consume_rate_limit_twice() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    payload = _payload(trip, [seat.id])
    first = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=payload,
        idempotency_key="rate-safe-replay",
        request=_request(key="rate-safe-replay"),
    )
    replay = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=payload,
        idempotency_key="rate-safe-replay",
        request=_request(key="rate-safe-replay"),
    )
    assert replay["hold_token"] == first["hold_token"]

    other_seat = trip.seats.exclude(id=seat.id).first()
    assert other_seat is not None
    with pytest.raises(DomainAPIException) as exc:
        create_public_seat_hold(
            trip_id=trip.public_id,
            payload=_payload(trip, [other_seat.id]),
            idempotency_key="rate-safe-new-attempt",
            request=_request(key="rate-safe-new-attempt"),
        )
    assert getattr(exc.value, "code", None) == "RATE_LIMITED"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=50)
def test_e05_ac03_map_does_not_authorize_stale_seat_selection() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    assert next(item for item in public_seat_map(trip)["seats"] if item["id"] == str(seat.id))["status"] == "available"
    booking = Booking.objects.create(
        office=trip.office,
        branch=trip.branch,
        trip=trip,
        source=Booking.Source.PUBLIC_WEB,
        status=Booking.Status.CONFIRMED,
        payment_status=Booking.PaymentStatus.PAID,
        contact_name="راكب",
        contact_phone="+963944000000",
        currency=trip.currency,
        subtotal_amount=trip.base_price,
        total_amount=trip.base_price,
        paid_amount=trip.base_price,
        policy_snapshot=trip.policy_snapshot,
        pricing_snapshot=trip.pricing_snapshot,
        manage_token_hash=uuid.uuid4().bytes,
    )
    passenger = BookingPassenger.objects.create(
        booking=booking,
        sequence_no=1,
        full_name="راكب",
        gender=BookingPassenger.Gender.MALE,
    )
    SeatAssignment.objects.create(
        trip=trip,
        booking=booking,
        passenger=passenger,
        trip_seat=seat,
        price_amount=trip.base_price,
    )
    with pytest.raises(DomainAPIException) as exc:
        create_public_seat_hold(
            trip_id=trip.public_id,
            payload=_payload(trip, [seat.id]),
            idempotency_key="stale-seat-key",
            request=_request(key="stale-seat-key"),
        )
    assert getattr(exc.value, "code", None) == "SEAT_NOT_AVAILABLE"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=50)
def test_hold_release_and_expiry_restore_availability() -> None:
    trip = _bookable_trip()
    seats = list(trip.seats.all()[:2])
    response = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=_payload(trip, [seat.id for seat in seats]),
        idempotency_key="release-hold-key",
        request=_request(key="release-hold-key"),
    )
    assert release_public_seat_hold(hold_token=response["hold_token"]) is True
    assert release_public_seat_hold(hold_token=response["hold_token"]) is False
    assert all(item["status"] == "available" for item in public_seat_map(trip)["seats"])

    response2 = create_public_seat_hold(
        trip_id=trip.public_id,
        payload=_payload(trip, [seats[0].id]),
        idempotency_key="expire-hold-key",
        request=_request(key="expire-hold-key"),
    )
    expiring_hold = SeatHold.objects.get(owner_booking_draft_id=uuid.UUID(response2["hold_token"].split(".", 1)[0]))
    expiring_hold.expires_at = expiring_hold.created_at + timedelta(seconds=1)
    expiring_hold.save(update_fields=["expires_at"])
    assert expire_due_holds(now=expiring_hold.created_at + timedelta(seconds=2)) == 1
    assert (
        next(item for item in public_seat_map(trip)["seats"] if item["id"] == str(seats[0].id))["status"] == "available"
    )


def test_public_api_search_hold_and_release_contract(api_client) -> None:  # type: ignore[no-untyped-def]
    trip = _bookable_trip()
    local_date = trip.scheduled_departure_at.astimezone(timezone.get_fixed_timezone(180)).date()
    locations = api_client.get("/v1/public/locations")
    assert locations.status_code == 200
    assert {"id", "name", "type", "address"} <= set(locations.data[0])

    search = api_client.get(
        "/v1/public/trips/search",
        {
            "origin_id": trip.route.origin_location.public_id,
            "destination_id": trip.route.destination_location.public_id,
            "date": local_date.isoformat(),
            "passengers": 1,
        },
    )
    assert search.status_code == 200
    assert search.data[0]["id"] == trip.public_id
    seat_id = str(trip.seats.first().id)
    hold = api_client.post(
        f"/v1/public/trips/{trip.public_id}/seat-holds",
        {
            "seat_ids": [seat_id],
            "passengers": [
                {
                    "full_name": "راكب الواجهة",
                    "gender": "male",
                    "passenger_type": "adult",
                    "seat_id": seat_id,
                }
            ],
            "quote_version": trip.version,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-hold-contract",
    )
    assert hold.status_code == 200
    assert hold.data["quote"]["total"]["currency"] == "SYP"
    release = api_client.post(
        f"/v1/public/seat-holds/{hold.data['hold_token']}/release",
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-release-contract",
    )
    assert release.status_code == 200
    assert release.data == {"released": True}


@pytest.mark.django_db(transaction=True)
def test_e06_ac01_postgresql_concurrent_hold_has_single_winner() -> None:
    from concurrent.futures import ThreadPoolExecutor

    from django import db
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock and partial-unique gate runs in CI")
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    payload = _payload(trip, [seat.id])

    def attempt(index: int) -> str:
        db.connections.close_all()
        try:
            create_public_seat_hold(
                trip_id=trip.public_id,
                payload=payload,
                idempotency_key=f"concurrent-hold-{index}",
                request=_request(key=f"concurrent-hold-{index}"),
            )
            return "won"
        except Exception as exc:  # pragma: no branch - exact split asserted below
            return str(getattr(exc, "code", type(exc).__name__))
        finally:
            db.connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(attempt, (1, 2)))
    assert outcomes.count("won") == 1
    assert outcomes.count("SEAT_NOT_AVAILABLE") == 1
    assert SeatHold.objects.filter(trip=trip, status=SeatHold.Status.ACTIVE).count() == 1
