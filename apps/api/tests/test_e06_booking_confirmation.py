from __future__ import annotations

import threading
import uuid
from datetime import timedelta

import pytest
from django import db
from django.db import connection
from django.test import RequestFactory, override_settings
from django.utils import timezone

from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import create_public_booking, create_public_seat_hold, manage_token_matches
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey
from fleet.models import SeatAdjacency
from trips.models import SeatHold, Trip

from .test_e05_public_search_holds import _bookable_trip, _request

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _add_same_unit_adjacency(trip: Trip, first_code: str = "1A", second_code: str = "1B") -> None:
    seats = {seat.seat_code: seat for seat in trip.seat_layout.seats.all()}
    first, second = sorted((seats[first_code], seats[second_code]), key=lambda item: item.id)
    SeatAdjacency.objects.create(
        layout=trip.seat_layout,
        seat_a=first,
        seat_b=second,
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
    )


def _hold(
    trip: Trip,
    *,
    seats: list,
    genders: list[str] | None = None,
    passenger_types: list[str] | None = None,
    key: str | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    genders = genders or ["male"] * len(seats)
    passenger_types = passenger_types or ["adult"] * len(seats)
    passengers = [
        {
            "full_name": f"مسافر {index}",
            "gender": genders[index - 1],
            "passenger_type": passenger_types[index - 1],
            "seat_id": seat.id,
        }
        for index, seat in enumerate(seats, start=1)
    ]
    idempotency_key = key or f"hold-{uuid.uuid4()}"
    response = create_public_seat_hold(
        trip_id=trip.public_id,
        payload={
            "seat_ids": [seat.id for seat in seats],
            "passengers": passengers,
            "quote_version": trip.version,
        },
        idempotency_key=idempotency_key,
        request=_request(key=idempotency_key),
    )
    return response, passengers


def _booking_payload(
    trip: Trip,
    hold: dict[str, object],
    passengers: list[dict[str, object]],
    *,
    payment_method: str = "office_cash",
) -> dict[str, object]:
    return {
        "trip_id": trip.public_id,
        "hold_token": hold["hold_token"],
        "contact": {
            "name": "محمد المسافر",
            "phone": "0944 123 456",
            "email": "guest@example.com",
        },
        "passengers": passengers,
        "payment_method": payment_method,
        "accepted_policy_version_ids": hold["quote"]["policy_version_ids"],
        "client_reference": "web-checkout-1",
    }


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e06_hold_is_consumed_atomically_and_booking_snapshots_are_frozen() -> None:
    trip = _bookable_trip()
    seats = list(trip.seats.all()[:2])
    hold, passengers = _hold(trip, seats=seats)
    payload = _booking_payload(trip, hold, passengers)

    result = create_public_booking(
        payload=payload,
        idempotency_key="booking-confirmation-1",
        request=_request(key="booking-confirmation-1"),
    )

    booking = Booking.objects.get(public_id=result["id"])
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.payment_status == Booking.PaymentStatus.UNPAID
    assert booking.contact_phone == "+963944123456"
    assert len(booking.terms_version_ids) == 3
    assert booking.pricing_snapshot["quote_version"] == trip.version
    assert booking.pricing_snapshot["payment_method"] == "office_cash"
    assert booking.total_amount == 211000
    assert booking.passengers.count() == 2
    assert booking.seat_assignments.filter(status=SeatAssignment.Status.ACTIVE).count() == 2
    assert SeatHold.objects.filter(owner_booking_draft_id__isnull=False, status=SeatHold.Status.CONSUMED).count() == 2
    assert result["pnr"] == booking.pnr
    assert result["manage_token"].startswith("mb1_")
    assert bytes(booking.manage_token_hash) != result["manage_token"].encode()
    assert manage_token_matches(booking, str(result["manage_token"])) is True
    assert manage_token_matches(booking, "mb1_invalid") is False

    frozen_pricing = dict(booking.pricing_snapshot)
    frozen_policy = dict(booking.policy_snapshot)
    trip.pricing_snapshot = {**trip.pricing_snapshot, "base_price": "999999.00"}
    trip.policy_snapshot = {"changed": True}
    trip.save(update_fields=["pricing_snapshot", "policy_snapshot"])
    booking.refresh_from_db()
    assert booking.pricing_snapshot == frozen_pricing
    assert booking.policy_snapshot == frozen_policy


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e06_expired_hold_is_rejected_without_consuming_resold_seat() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat])
    token_batch = uuid.UUID(str(hold["hold_token"]).split(".", 1)[0])
    SeatHold.objects.filter(owner_booking_draft_id=token_batch).update(
        created_at=timezone.now() - timedelta(minutes=2),
        expires_at=timezone.now() - timedelta(minutes=1),
    )

    with pytest.raises(DomainAPIException) as exc:
        create_public_booking(
            payload=_booking_payload(trip, hold, passengers),
            idempotency_key="expired-booking-1",
            request=_request(key="expired-booking-1"),
        )
    assert exc.value.code == "SEAT_HOLD_EXPIRED"
    assert Booking.objects.count() == 0
    assert SeatAssignment.objects.count() == 0
    replacement, _ = _hold(trip, seats=[seat], key="replacement-after-expiry")
    assert replacement["hold_token"] != hold["hold_token"]
    assert SeatHold.objects.filter(trip=trip, trip_seat=seat, status=SeatHold.Status.ACTIVE).count() == 1


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e06_gender_conflict_is_private_across_bookings_but_allowed_inside_one_booking() -> None:
    trip = _bookable_trip()
    _add_same_unit_adjacency(trip)
    seats = list(trip.seats.order_by("seat_code")[:2])

    first_hold, first_passengers = _hold(trip, seats=[seats[0]], genders=["male"])
    create_public_booking(
        payload=_booking_payload(trip, first_hold, first_passengers),
        idempotency_key="gender-first-booking",
        request=_request(key="gender-first-booking"),
    )

    second_hold, second_passengers = _hold(trip, seats=[seats[1]], genders=["female"])
    with pytest.raises(DomainAPIException) as exc:
        create_public_booking(
            payload=_booking_payload(trip, second_hold, second_passengers),
            idempotency_key="gender-second-booking",
            request=_request(key="gender-second-booking"),
        )
    assert exc.value.code == "SEAT_GENDER_CONFLICT"
    assert "gender" not in str(exc.value.details).lower()

    other_trip = _bookable_trip()
    _add_same_unit_adjacency(other_trip)
    mixed_seats = list(other_trip.seats.order_by("seat_code")[:2])
    mixed_hold, mixed_passengers = _hold(
        other_trip,
        seats=mixed_seats,
        genders=["male", "female"],
    )
    mixed_result = create_public_booking(
        payload=_booking_payload(other_trip, mixed_hold, mixed_passengers),
        idempotency_key="gender-same-booking",
        request=_request(key="gender-same-booking"),
    )
    assert Booking.objects.get(public_id=mixed_result["id"]).passengers.count() == 2


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e06_child_guardian_group_is_snapshotted_and_boarding_states_remain_independent() -> None:
    trip = _bookable_trip()
    _add_same_unit_adjacency(trip)
    seats = list(trip.seats.order_by("seat_code")[:2])
    hold, passengers = _hold(
        trip,
        seats=seats,
        genders=["female", "female"],
        passenger_types=["adult", "child"],
    )
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers),
        idempotency_key="group-booking-1",
        request=_request(key="group-booking-1"),
    )
    booking = Booking.objects.get(public_id=result["id"])
    grouping = booking.policy_snapshot["passenger_grouping"]
    assert grouping["protected_groups"] == [{"dependent_sequence": 2, "guardian_sequence": 1}]
    assert grouping["requires_reassignment_review_for_sequences"] == []

    first, second = list(booking.passengers.order_by("sequence_no"))
    first.boarding_status = BookingPassenger.BoardingStatus.BOARDED
    first.save(update_fields=["boarding_status"])
    second.refresh_from_db()
    assert second.boarding_status == BookingPassenger.BoardingStatus.NOT_ARRIVED


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_public_booking_api_is_idempotent_and_returns_pnr_and_manage_token(api_client) -> None:  # type: ignore[no-untyped-def]
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat])
    payload = _booking_payload(trip, hold, passengers)

    first = api_client.post(
        "/v1/public/bookings",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="public-booking-contract",
    )
    second = api_client.post(
        "/v1/public/bookings",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="public-booking-contract",
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.data["id"] == second.data["id"]
    assert first.data["pnr"] == second.data["pnr"]
    assert first.data["manage_token"] == second.data["manage_token"]
    assert Booking.objects.count() == 1
    stored = IdempotencyKey.objects.get(scope_type="public_booking", key="public-booking-contract")
    assert "manage_token" not in (stored.response_body or {})


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_manual_transfer_booking_waits_for_payment_and_keeps_deadline_snapshot() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat])
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers, payment_method="manual_transfer"),
        idempotency_key="manual-transfer-booking",
        request=_request(key="manual-transfer-booking"),
    )
    booking = Booking.objects.get(public_id=result["id"])
    assert booking.status == Booking.Status.AWAITING_PAYMENT
    assert booking.confirmed_at is None
    assert booking.payment_deadline_at is not None
    assert result["payment_deadline_at"] is not None


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e06_ac01_parallel_confirmation_creates_only_one_active_assignment() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency gate")
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat])
    payload = _booking_payload(trip, hold, passengers)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(key: str) -> None:
        db.connections.close_all()
        barrier.wait()
        try:
            create_public_booking(
                payload=payload,
                idempotency_key=key,
                request=RequestFactory().post("/v1/public/bookings", REMOTE_ADDR="203.0.113.20"),
            )
            outcomes.append("ok")
        except DomainAPIException as exc:
            outcomes.append(exc.code)
        finally:
            db.connections.close_all()

    threads = [
        threading.Thread(target=worker, args=("parallel-booking-a",)),
        threading.Thread(target=worker, args=("parallel-booking-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("ok") == 1
    assert len(outcomes) == 2
    assert SeatAssignment.objects.filter(
        trip=trip,
        trip_seat=seat,
        status=SeatAssignment.Status.ACTIVE,
    ).count() == 1

@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_public_hold_requires_passenger_gender_with_catalog_error(api_client) -> None:  # type: ignore[no-untyped-def]
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None

    response = api_client.post(
        f"/v1/public/trips/{trip.public_id}/seat-holds",
        {
            "seat_ids": [str(seat.id)],
            "passengers": [
                {
                    "full_name": "مسافر بلا جنس",
                    "passenger_type": "adult",
                    "seat_id": str(seat.id),
                }
            ],
            "quote_version": trip.version,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="gender-required-contract",
    )

    assert response.status_code == 422
    assert response.data["error"]["code"] == "PASSENGER_GENDER_REQUIRED"
    assert SeatHold.objects.count() == 0
