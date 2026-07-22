from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from bookings.change_services import (
    cancel_public_booking,
    get_cancellation_quote,
    replace_booking_passenger,
)
from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import create_public_booking
from common.exceptions import DomainAPIException
from finance.models import Commission, LedgerEntry
from finance.services import assert_entry_balanced
from identity.models import User
from organizations.models import OfficeMembership
from organizations.services import OfficeContext
from payments.models import Chargeback, PaymentTransaction, Refund
from payments.refund_services import command_refund
from payments.services import record_office_cash_payment
from tickets.models import Ticket

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import (
    _add_same_unit_adjacency,
    _booking_payload,
    _hold,
)
from .test_e07_payments import _finance_context

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _paid_booking(*, passenger_count: int = 1) -> tuple[Booking, dict[str, object], OfficeContext, User]:
    trip = _bookable_trip()
    seats = list(trip.seats.order_by("seat_code")[:passenger_count])
    hold, passengers = _hold(
        trip,
        seats=seats,
        genders=["male"] * passenger_count,
        key=f"e09-hold-{uuid.uuid4()}",
    )
    created = create_public_booking(
        payload=_booking_payload(trip, hold, passengers, payment_method="office_cash"),
        idempotency_key=f"e09-booking-{uuid.uuid4()}",
        request=_request(key=f"e09-create-{uuid.uuid4()}"),
    )
    booking = Booking.objects.get(public_id=created["id"])
    context, actor = _finance_context(booking)
    record_office_cash_payment(
        context=context,
        actor=actor,
        request=_request(actor, key=f"e09-cash-{uuid.uuid4()}"),
        booking_id=booking.public_id,
        amount=booking.total_amount,
        receipt_number=f"E09-{uuid.uuid4().hex[:8]}",
        occurred_at=timezone.now(),
        idempotency_key=f"e09-cash-{uuid.uuid4()}",
    )
    booking.refresh_from_db()
    return booking, created, context, actor


def _set_cancellation_policy(
    booking: Booking,
    *,
    refund_percent: str = "80",
    allow_partial: bool = True,
    fixed_fee: str = "0",
) -> None:
    snapshot = dict(booking.policy_snapshot)
    cancellation = dict(snapshot.get("cancellation", {}))
    cancellation["rules"] = {
        "refund_percent": refund_percent,
        "allow_partial": allow_partial,
        "fixed_fee": fixed_fee,
    }
    snapshot["cancellation"] = cancellation
    booking.policy_snapshot = snapshot
    booking.save(update_fields=["policy_snapshot", "updated_at"])


def _second_actor(context: OfficeContext) -> tuple[OfficeContext, User]:
    user = User.objects.create_user(
        full_name="مدقق الاسترداد",
        email=f"refund-approver-{uuid.uuid4()}@example.com",
        password="SecurePass!234",
    )
    membership = OfficeMembership.objects.create(
        user=user,
        office=context.office,
        role=context.membership.role,
    )
    return (
        OfficeContext(
            membership=membership,
            permissions=frozenset({"office.refund.manage", "office.finance.view"}),
        ),
        user,
    )


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e09_ac01_cancellation_quote_uses_frozen_booking_policy_snapshot() -> None:
    booking, created, _, _ = _paid_booking()
    _set_cancellation_policy(booking, refund_percent="80")
    passenger = booking.passengers.get()

    quote = get_cancellation_quote(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        passenger_ids=[str(passenger.id)],
    )

    expected = (booking.total_amount * Decimal("0.80")).quantize(Decimal("0.01"))
    assert Decimal(str(quote["refund_amount"]["amount"])) == expected
    assert quote["reason"] == "snapshot_policy"
    assert str(quote["quote_token"]).startswith("cq1.")

    # Changing the trip's current policy after booking must not change the quote.
    booking.trip.policy_snapshot = {"cancellation": {"rules": {"refund_percent": "5"}}}
    booking.trip.save(update_fields=["policy_snapshot"])
    repeated = get_cancellation_quote(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        passenger_ids=[str(passenger.id)],
    )
    assert Decimal(str(repeated["refund_amount"]["amount"])) == expected


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e09_ac02_boarded_passenger_cannot_be_cancelled() -> None:
    booking, created, _, _ = _paid_booking()
    passenger = booking.passengers.get()
    passenger.boarding_status = BookingPassenger.BoardingStatus.BOARDED
    passenger.save(update_fields=["boarding_status"])

    with pytest.raises(DomainAPIException) as exc:
        get_cancellation_quote(
            pnr=booking.pnr,
            manage_token=str(created["manage_token"]),
            passenger_ids=[str(passenger.id)],
        )
    assert exc.value.code == "PASSENGER_ALREADY_BOARDED"


@override_settings(
    PUBLIC_HOLD_RATE_LIMIT=100,
    PUBLIC_BOOKING_RATE_LIMIT=100,
    REFUND_DUAL_APPROVAL_THRESHOLD="999999999.00",
)
def test_e09_ac03_partial_cancellation_releases_only_selected_seat_and_refunds_it() -> None:
    booking, created, context, _ = _paid_booking(passenger_count=2)
    _set_cancellation_policy(booking, refund_percent="80", allow_partial=True)
    selected, untouched = list(booking.passengers.order_by("sequence_no"))
    original_total = booking.total_amount

    quote = get_cancellation_quote(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        passenger_ids=[str(selected.id)],
    )
    cancel_public_booking(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        quote_token=str(quote["quote_token"]),
        reason_code="customer_request",
        idempotency_key="e09-partial-cancel",
        request=_request(key="e09-partial-cancel"),
    )

    booking.refresh_from_db()
    selected.refresh_from_db()
    untouched.refresh_from_db()
    refund = Refund.objects.get(booking=booking, passenger=selected)
    commission = Commission.objects.get(booking=booking)
    selected_assignment = SeatAssignment.objects.get(booking=booking, passenger=selected)
    untouched_assignment = SeatAssignment.objects.get(booking=booking, passenger=untouched)

    assert selected.status == BookingPassenger.Status.CANCELLED
    assert selected_assignment.status == SeatAssignment.Status.CANCELLED
    assert not Ticket.objects.filter(passenger=selected, status=Ticket.Status.ACTIVE).exists()
    assert untouched.status == BookingPassenger.Status.ACTIVE
    assert untouched_assignment.status == SeatAssignment.Status.ACTIVE
    assert Ticket.objects.filter(passenger=untouched, status=Ticket.Status.ACTIVE).exists()
    assert booking.total_amount < original_total
    assert booking.status == Booking.Status.CONFIRMED
    assert commission.status == Commission.Status.ADJUSTED
    assert refund.passenger_id == selected.id

    approver_context, approver = _second_actor(context)
    command_refund(
        refund_id=refund.id,
        command="review",
        actor=approver,
        request=_request(approver, key="e09-refund-review"),
        idempotency_key="e09-refund-review",
        data={},
        context=approver_context,
    )
    command_refund(
        refund_id=refund.id,
        command="approve",
        actor=approver,
        request=_request(approver, key="e09-refund-approve"),
        idempotency_key="e09-refund-approve",
        data={},
        context=approver_context,
    )
    command_refund(
        refund_id=refund.id,
        command="process",
        actor=approver,
        request=_request(approver, key="e09-refund-process"),
        idempotency_key="e09-refund-process",
        data={},
        context=approver_context,
    )
    command_refund(
        refund_id=refund.id,
        command="succeed",
        actor=approver,
        request=_request(approver, key="e09-refund-succeed"),
        idempotency_key="e09-refund-succeed",
        data={"provider_reference": "RF-E09-001"},
        context=approver_context,
    )

    booking.refresh_from_db()
    refund.refresh_from_db()
    assert refund.status == Refund.Status.SUCCEEDED
    assert booking.payment_status == Booking.PaymentStatus.PARTIALLY_REFUNDED
    assert booking.refunded_amount == refund.approved_amount
    for entry in LedgerEntry.objects.filter(event_id=refund.id):
        assert_entry_balanced(entry)


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e09_ac04_refund_requester_cannot_approve_own_high_value_refund() -> None:
    booking, _, context, actor = _paid_booking()
    passenger = booking.passengers.get()
    refund = Refund.objects.create(
        booking=booking,
        passenger=passenger,
        status=Refund.Status.UNDER_REVIEW,
        reason_code="customer_request",
        requested_amount=booking.paid_amount,
        currency=booking.currency,
        requested_by=actor,
    )

    with pytest.raises(DomainAPIException) as exc:
        command_refund(
            refund_id=refund.id,
            command="approve",
            actor=actor,
            request=_request(actor, key="e09-self-approve"),
            idempotency_key="e09-self-approve",
            data={"approved_amount": str(refund.requested_amount)},
            context=context,
        )
    assert exc.value.code == "DUAL_APPROVAL_REQUIRED"


@override_settings(
    PUBLIC_HOLD_RATE_LIMIT=100,
    PUBLIC_BOOKING_RATE_LIMIT=100,
    REFUND_DUAL_APPROVAL_THRESHOLD="999999999.00",
)
def test_e09_ac05_open_chargeback_blocks_refund_and_double_compensation() -> None:
    booking, _, context, _ = _paid_booking()
    passenger = booking.passengers.get()
    transaction = PaymentTransaction.objects.get(payment_intent__booking=booking)
    refund = Refund.objects.create(
        booking=booking,
        passenger=passenger,
        status=Refund.Status.UNDER_REVIEW,
        reason_code="customer_request",
        requested_amount=booking.paid_amount,
        currency=booking.currency,
    )
    Chargeback.objects.create(
        payment_transaction=transaction,
        provider_case_id=f"CB-{uuid.uuid4()}",
        status=Chargeback.Status.OPEN,
        amount=booking.paid_amount,
        currency=booking.currency,
        opened_at=timezone.now(),
    )
    approver_context, approver = _second_actor(context)

    with pytest.raises(DomainAPIException) as exc:
        command_refund(
            refund_id=refund.id,
            command="approve",
            actor=approver,
            request=_request(approver, key="e09-chargeback-block"),
            idempotency_key="e09-chargeback-block",
            data={},
            context=approver_context,
        )
    assert exc.value.code == "CHARGEBACK_OPEN"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e09_ac06_passenger_gender_replacement_rechecks_adjacency() -> None:
    trip = _bookable_trip()
    _add_same_unit_adjacency(trip)
    seats = list(trip.seats.order_by("seat_code")[:2])

    first_hold, first_passengers = _hold(trip, seats=[seats[0]], genders=["male"])
    create_public_booking(
        payload=_booking_payload(trip, first_hold, first_passengers),
        idempotency_key="e09-adjacency-first",
        request=_request(key="e09-adjacency-first"),
    )
    second_hold, second_passengers = _hold(trip, seats=[seats[1]], genders=["male"])
    second_created = create_public_booking(
        payload=_booking_payload(trip, second_hold, second_passengers),
        idempotency_key="e09-adjacency-second",
        request=_request(key="e09-adjacency-second"),
    )
    booking = Booking.objects.get(public_id=second_created["id"])
    passenger = booking.passengers.get()
    membership = booking.trip.created_by.office_memberships.get(office=booking.office)
    context = OfficeContext(
        membership=membership,
        permissions=frozenset({"office.booking.manage"}),
    )

    with pytest.raises(DomainAPIException) as exc:
        replace_booking_passenger(
            context=context,
            actor=booking.trip.created_by,
            request=_request(booking.trip.created_by, key="e09-replace-gender"),
            booking_id=booking.public_id,
            passenger_id=passenger.id,
            data={"gender": "female", "full_name": "مسافرة بديلة"},
            idempotency_key="e09-replace-gender",
        )
    assert exc.value.code == "SEAT_GENDER_CONFLICT"
    passenger.refresh_from_db()
    assert passenger.gender == BookingPassenger.Gender.MALE

@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_public_cancellation_api_contract_is_idempotent(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created, _, _ = _paid_booking()
    _set_cancellation_policy(booking, refund_percent="75")
    passenger = booking.passengers.get()
    token = str(created["manage_token"])

    quote_response = api_client.get(
        f"/v1/public/bookings/{booking.pnr}/cancellation-quote",
        {
            "manage_token": token,
            "passenger_id": str(passenger.id),
        },
    )
    assert quote_response.status_code == 200
    assert quote_response.data["allowed"] is True

    url = f"/v1/public/bookings/{booking.pnr}/cancel?manage_token={token}"
    payload = {
        "quote_token": quote_response.data["quote_token"],
        "reason_code": "customer_request",
    }
    first = api_client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="e09-api-cancel")
    replay = api_client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="e09-api-cancel")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.data["id"] == replay.data["id"]
    assert first.data["passengers"] == replay.data["passengers"]
    assert Refund.objects.filter(booking=booking).count() == 1
