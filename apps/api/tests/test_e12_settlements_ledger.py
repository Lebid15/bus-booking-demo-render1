from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from bookings.models import Booking
from bookings.services import create_public_booking
from common.exceptions import DomainAPIException
from finance.models import (
    Commission,
    FinancialDispute,
    LedgerAccount,
    LedgerEntry,
    LedgerPosting,
    Settlement,
    SettlementItem,
)
from finance.services import (
    PostingSpec,
    calculate_settlement,
    command_settlement,
    create_settlement,
    post_electronic_capture_entry,
    post_ledger_entry,
    recognize_booking_service,
    reverse_ledger_entry,
)
from identity.models import User, UserSession
from organizations.models import OfficePayoutAccount
from organizations.services import OfficeContext
from payments.models import PaymentIntent, PaymentTransaction
from payments.services import record_office_cash_payment
from trips.models import Trip

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import _booking_payload, _hold

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _platform_user(label: str) -> User:
    return User.objects.create_user(
        full_name=label,
        email=f"{label.lower().replace(' ', '.')}@example.com",
        is_platform_staff=True,
    )


def _mfa_request(user: User, key: str):  # type: ignore[no-untyped-def]
    request = RequestFactory().post(
        "/v1/platform/settlements",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="203.0.113.212",
    )
    request.user = user
    request.auth = UserSession.objects.create(
        user=user,
        token_hash=f"token-{uuid.uuid4()}".encode(),
        expires_at=timezone.now() + timedelta(hours=2),
        mfa_verified_at=timezone.now(),
    )
    return request


def _finance_context(booking: Booking) -> tuple[OfficeContext, User]:
    actor = booking.trip.created_by
    membership = actor.office_memberships.get(office=booking.office)
    return (
        OfficeContext(
            membership=membership,
            permissions=frozenset({"office.payment.confirm_manual", "office.finance.view"}),
        ),
        actor,
    )


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def _paid_booking(*, method: str, currency: str = "SYP", recognize: bool = True) -> Booking:
    trip = _bookable_trip()
    trip.currency = currency
    trip.pricing_snapshot = {
        **trip.pricing_snapshot,
        "payment_methods": ["office_cash", "manual_transfer", "electronic"],
        "commission": {"rate": "0.100000", "fixed_amount": "0.00"},
    }
    trip.save(update_fields=["currency", "pricing_snapshot"])
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key=f"e12-hold-{uuid.uuid4()}")
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers, payment_method=method),
        idempotency_key=f"e12-booking-{uuid.uuid4()}",
        request=_request(key=f"e12-request-{uuid.uuid4()}"),
    )
    booking = Booking.objects.get(public_id=result["id"])
    if method == PaymentIntent.MethodType.ELECTRONIC:
        intent = PaymentIntent.objects.create(
            booking=booking,
            method_type=method,
            status=PaymentIntent.Status.SUCCEEDED,
            amount=booking.total_amount,
            currency=booking.currency,
            provider_code="sandbox",
            provider_reference=f"psp-{uuid.uuid4()}",
            idempotency_key=f"intent-{uuid.uuid4()}",
        )
        tx = PaymentTransaction.objects.create(
            payment_intent=intent,
            transaction_type=PaymentTransaction.TransactionType.CAPTURE,
            status=PaymentTransaction.Status.SUCCEEDED,
            amount=booking.total_amount,
            currency=booking.currency,
            provider_event_id=f"event-{uuid.uuid4()}",
            occurred_at=timezone.now(),
        )
        post_electronic_capture_entry(
            transaction_id=tx.id,
            booking=booking,
            amount=booking.total_amount,
            occurred_at=tx.occurred_at,
        )
        booking.status = Booking.Status.CONFIRMED
        booking.payment_status = Booking.PaymentStatus.PAID
        booking.paid_amount = booking.total_amount
        booking.confirmed_at = timezone.now()
        booking.save(update_fields=["status", "payment_status", "paid_amount", "confirmed_at", "updated_at"])
    else:
        context, actor = _finance_context(booking)
        record_office_cash_payment(
            context=context,
            actor=actor,
            request=_request(actor, key=f"cash-{uuid.uuid4()}"),
            booking_id=booking.public_id,
            amount=booking.total_amount,
            receipt_number=f"RCPT-{uuid.uuid4().hex[:10]}",
            occurred_at=timezone.now(),
            idempotency_key=f"cash-{uuid.uuid4()}",
        )
        booking.refresh_from_db()
    commission = Commission.objects.get(booking=booking)
    commission.rate = Decimal("0.100000")
    commission.fixed_amount = Decimal("0.00")
    commission.commission_amount = (booking.total_amount * Decimal("0.10")).quantize(Decimal("0.01"))
    commission.save(update_fields=["rate", "fixed_amount", "commission_amount"])
    occurred = timezone.now() - timedelta(days=1)
    trip.status = Trip.Status.COMPLETED
    trip.actual_arrival_at = occurred
    trip.save(update_fields=["status", "actual_arrival_at", "updated_at"])
    if recognize:
        recognize_booking_service(booking=booking, occurred_at=occurred)
    booking.refresh_from_db()
    return booking


def _settlement_for(booking: Booking, creator: User, *, currency: str | None = None) -> Settlement:
    day = timezone.localdate() - timedelta(days=1)
    return create_settlement(
        actor=creator,
        office_id=booking.office.public_id,
        period_start=day,
        period_end=day,
        currency=currency or booking.currency,
        idempotency_key=f"settlement-{uuid.uuid4()}",
        request=None,
    )


def _active_payout(booking: Booking, creator: User) -> OfficePayoutAccount:
    return OfficePayoutAccount.objects.create(
        office=booking.office,
        method_type=OfficePayoutAccount.MethodType.BANK,
        account_holder_name="Test Office",
        account_reference_ciphertext=b"encrypted-account",
        account_reference_last4="1234",
        status=OfficePayoutAccount.Status.ACTIVE,
        verified_at=timezone.now() - timedelta(days=1),
        effective_at=timezone.now() - timedelta(hours=1),
        created_by=creator,
        approved_by=_platform_user(f"Payout Approver {uuid.uuid4().hex[:6]}"),
    )


def test_e12_ac01_unbalanced_entry_is_rejected_before_posting() -> None:
    booking = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC, recognize=False)
    with pytest.raises(DomainAPIException) as exc:
        post_ledger_entry(
            event_type="BROKEN_ENTRY",
            event_id=uuid.uuid4(),
            currency=booking.currency,
            office=booking.office,
            booking=booking,
            occurred_at=timezone.now(),
            description="must fail",
            postings=[
                PostingSpec(
                    account_code="1000_BANK",
                    account_type=LedgerAccount.AccountType.ASSET,
                    direction=LedgerPosting.Direction.DEBIT,
                    amount=Decimal("100.00"),
                ),
                PostingSpec(
                    account_code="2000_CUSTOMER_FUNDS",
                    account_type=LedgerAccount.AccountType.LIABILITY,
                    direction=LedgerPosting.Direction.CREDIT,
                    amount=Decimal("90.00"),
                ),
            ],
        )
    assert exc.value.code == "LEDGER_UNBALANCED"
    assert not LedgerEntry.objects.filter(event_type="BROKEN_ENTRY").exists()


def test_e12_ac02_electronic_capture_records_customer_funds_not_commission_revenue() -> None:
    booking = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC, recognize=False)
    entry = LedgerEntry.objects.get(event_type="ELECTRONIC_PAYMENT_CAPTURED", booking=booking)
    codes = set(entry.postings.values_list("account__code", flat=True))
    assert codes == {"1010_PSP_RECEIVABLE", "2000_CUSTOMER_FUNDS"}
    assert "4000_COMMISSION_REVENUE" not in codes
    assert Commission.objects.get(booking=booking).status == Commission.Status.EXPECTED


def test_e12_ac03_direct_payment_completion_creates_office_commission_receivable() -> None:
    booking = _paid_booking(method=PaymentIntent.MethodType.OFFICE_CASH)
    commission = Commission.objects.get(booking=booking)
    entry = LedgerEntry.objects.get(event_type="COMMISSION_EARNED_DIRECT", booking=booking)
    receivable = entry.postings.get(account__code="1020_OFFICE_COMMISSION_RECEIVABLE")
    revenue = entry.postings.get(account__code="4000_COMMISSION_REVENUE")
    assert receivable.direction == LedgerPosting.Direction.DEBIT
    assert revenue.direction == LedgerPosting.Direction.CREDIT
    assert receivable.amount == commission.commission_amount
    assert commission.status == Commission.Status.EARNED


def test_e12_ac04_settlement_nets_electronic_payable_and_direct_commission_same_currency_only() -> None:
    electronic = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC, currency="SYP")
    direct = _paid_booking(method=PaymentIntent.MethodType.OFFICE_CASH, currency="SYP")
    # Move the second booking into the same office so both balances belong to one settlement.
    direct.office = electronic.office
    direct.trip.office = electronic.office
    direct.trip.save(update_fields=["office", "updated_at"])
    direct.save(update_fields=["office", "updated_at"])
    Commission.objects.filter(booking=direct).update(office=electronic.office)
    other_currency = _paid_booking(method=PaymentIntent.MethodType.OFFICE_CASH, currency="USD")
    other_currency.office = electronic.office
    other_currency.trip.office = electronic.office
    other_currency.trip.save(update_fields=["office", "updated_at"])
    other_currency.save(update_fields=["office", "updated_at"])
    Commission.objects.filter(booking=other_currency).update(office=electronic.office)

    creator = _platform_user("Settlement Creator")
    settlement = _settlement_for(electronic, creator, currency="SYP")
    calculated = calculate_settlement(settlement)
    direct_commission = Commission.objects.get(booking=direct).commission_amount
    electronic_commission = Commission.objects.get(booking=electronic).commission_amount
    expected_payable = electronic.paid_amount - electronic.refunded_amount - electronic_commission
    assert calculated.net_amount == expected_payable - direct_commission
    assert calculated.items.filter(item_type=SettlementItem.ItemType.NETTING).get().amount == direct_commission
    assert not calculated.items.filter(booking=other_currency).exists()
    assert Commission.objects.get(booking=other_currency).status == Commission.Status.EARNED


def test_e12_ac05_only_disputed_booking_amount_is_frozen_from_settlement() -> None:
    disputed = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC)
    clean = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC)
    clean.office = disputed.office
    clean.trip.office = disputed.office
    clean.trip.save(update_fields=["office", "updated_at"])
    clean.save(update_fields=["office", "updated_at"])
    Commission.objects.filter(booking=clean).update(office=disputed.office)
    frozen = Decimal("2500.00")
    FinancialDispute.objects.create(
        booking=disputed,
        category="customer_service_dispute",
        disputed_amount=frozen,
        currency=disputed.currency,
        opened_by_type=FinancialDispute.OpenedByType.CUSTOMER,
    )
    settlement = calculate_settlement(_settlement_for(disputed, _platform_user("Freeze Creator")))
    assert settlement.reserve_amount == frozen
    frozen_item = settlement.items.get(item_type=SettlementItem.ItemType.FROZEN_DISPUTE)
    assert frozen_item.booking_id == disputed.id
    assert frozen_item.amount == frozen
    clean_item = settlement.items.get(
        item_type=SettlementItem.ItemType.ELECTRONIC_PAYABLE,
        booking=clean,
    )
    assert clean_item.amount > 0
    assert settlement.net_amount == (
        sum(
            (item.amount for item in settlement.items.filter(item_type=SettlementItem.ItemType.ELECTRONIC_PAYABLE)),
            Decimal("0.00"),
        )
        - frozen
    )


def test_e12_ac06_correction_creates_reversal_without_editing_original_entry() -> None:
    booking = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC, recognize=False)
    original = LedgerEntry.objects.get(event_type="ELECTRONIC_PAYMENT_CAPTURED", booking=booking)
    snapshot = list(original.postings.values_list("account__code", "direction", "amount"))
    reversal = reverse_ledger_entry(
        original=original,
        event_id=uuid.uuid4(),
        description="Correct provider duplicate capture",
    )
    original.refresh_from_db()
    assert original.status == LedgerEntry.Status.POSTED
    assert original.reversal_of_id is None
    assert list(original.postings.values_list("account__code", "direction", "amount")) == snapshot
    assert reversal.reversal_of_id == original.id
    assert reversal.status == LedgerEntry.Status.REVERSED
    for posting in original.postings.all():
        inverse = reversal.postings.get(account__code=posting.account.code)
        assert inverse.amount == posting.amount
        assert inverse.direction != posting.direction


def test_e12_ac07_creator_cannot_approve_own_settlement_but_second_mfa_user_can() -> None:
    booking = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC)
    creator = _platform_user("Dual Creator")
    approver = _platform_user("Dual Approver")
    _active_payout(booking, creator)
    settlement = calculate_settlement(_settlement_for(booking, creator))
    settlement = command_settlement(
        settlement=settlement,
        actor=creator,
        command="submit_review",
        payment_reference=None,
        idempotency_key="submit-settlement-review",
        request=_mfa_request(creator, "submit-settlement-review"),
    )
    with pytest.raises(DomainAPIException) as exc:
        command_settlement(
            settlement=settlement,
            actor=creator,
            command="approve",
            payment_reference=None,
            idempotency_key="self-approve-settlement",
            request=_mfa_request(creator, "self-approve-settlement"),
        )
    assert exc.value.code == "DUAL_APPROVAL_REQUIRED"
    approved = command_settlement(
        settlement=settlement,
        actor=approver,
        command="approve",
        payment_reference=None,
        idempotency_key="second-approve-settlement",
        request=_mfa_request(approver, "second-approve-settlement"),
    )
    assert approved.status == Settlement.Status.APPROVED
    assert approved.approved_by_id == approver.id


def test_settlement_payment_posts_same_currency_netting_and_payout() -> None:
    electronic = _paid_booking(method=PaymentIntent.MethodType.ELECTRONIC)
    direct = _paid_booking(method=PaymentIntent.MethodType.OFFICE_CASH)
    direct.office = electronic.office
    direct.trip.office = electronic.office
    direct.trip.save(update_fields=["office", "updated_at"])
    direct.save(update_fields=["office", "updated_at"])
    Commission.objects.filter(booking=direct).update(office=electronic.office)
    creator = _platform_user("Payment Cycle Creator")
    approver = _platform_user("Payment Cycle Approver")
    _active_payout(electronic, creator)
    settlement = calculate_settlement(_settlement_for(electronic, creator))
    settlement = command_settlement(
        settlement=settlement,
        actor=creator,
        command="submit_review",
        payment_reference=None,
        idempotency_key="payment-cycle-review",
        request=_mfa_request(creator, "payment-cycle-review"),
    )
    settlement = command_settlement(
        settlement=settlement,
        actor=approver,
        command="approve",
        payment_reference=None,
        idempotency_key="payment-cycle-approve",
        request=_mfa_request(approver, "payment-cycle-approve"),
    )
    settlement = command_settlement(
        settlement=settlement,
        actor=approver,
        command="process",
        payment_reference=None,
        idempotency_key="payment-cycle-process",
        request=_mfa_request(approver, "payment-cycle-process"),
    )
    paid = command_settlement(
        settlement=settlement,
        actor=approver,
        command="mark_paid",
        payment_reference="PAYOUT-E12-001",
        idempotency_key="payment-cycle-paid",
        request=_mfa_request(approver, "payment-cycle-paid"),
    )
    assert paid.status == Settlement.Status.PAID
    assert LedgerEntry.objects.filter(event_type="DIRECT_COMMISSION_NETTED", event_id=paid.id).exists()
    assert LedgerEntry.objects.filter(event_type="SETTLEMENT_PAID", event_id=paid.id).exists()
    for entry in LedgerEntry.objects.filter(event_id=paid.id):
        debit = sum(
            (posting.amount for posting in entry.postings.all() if posting.direction == LedgerPosting.Direction.DEBIT),
            Decimal("0.00"),
        )
        credit = sum(
            (posting.amount for posting in entry.postings.all() if posting.direction == LedgerPosting.Direction.CREDIT),
            Decimal("0.00"),
        )
        assert debit == credit
    unsettled_commissions = Commission.objects.filter(settlement_items__settlement=paid).exclude(
        status=Commission.Status.PAID
    )
    assert not unsettled_commissions.exists()
