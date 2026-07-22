from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from auditlog.models import AuditLog
from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import create_public_booking
from common.exceptions import DomainAPIException
from finance.models import Commission, LedgerEntry
from finance.services import assert_entry_balanced
from identity.models import Permission, User
from organizations.services import OfficeContext
from payments.models import (
    ManualPaymentSubmission,
    PaymentIntent,
    PaymentReconciliationCase,
    PaymentTransaction,
    WebhookDelivery,
)
from payments.services import (
    create_public_payment_intent,
    expire_due_unpaid_bookings,
    process_received_webhook_deliveries,
    record_office_cash_payment,
    submit_manual_transfer,
    verify_manual_payment,
)
from tickets.models import Ticket

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import _booking_payload, _hold

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _booking(*, payment_method: str) -> tuple[Booking, dict[str, object]]:
    trip = _bookable_trip()
    if payment_method == "electronic":
        trip.pricing_snapshot = {
            **trip.pricing_snapshot,
            "payment_methods": ["office_cash", "manual_transfer", "electronic"],
        }
        trip.save(update_fields=["pricing_snapshot"])
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key=f"e07-hold-{uuid.uuid4()}")
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers, payment_method=payment_method),
        idempotency_key=f"e07-booking-{uuid.uuid4()}",
        request=_request(key=f"e07-request-{uuid.uuid4()}"),
    )
    return Booking.objects.get(public_id=result["id"]), result


def _finance_context(booking: Booking) -> tuple[OfficeContext, User]:
    membership = booking.trip.created_by.office_memberships.get(office=booking.office)
    permission, _ = Permission.objects.get_or_create(
        code="office.payment.confirm_manual",
        defaults={"name_ar": "تأكيد الدفع اليدوي", "risk_level": Permission.RiskLevel.CRITICAL},
    )
    membership.role.permissions.add(permission)
    context = OfficeContext(
        membership=membership,
        permissions=frozenset({"office.payment.confirm_manual", "office.finance.view"}),
    )
    return context, booking.trip.created_by


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e07_ac01_office_cash_creates_one_transaction_balanced_ledger_receipt_and_audit() -> None:
    booking, _ = _booking(payment_method="office_cash")
    context, actor = _finance_context(booking)

    first = record_office_cash_payment(
        context=context,
        actor=actor,
        request=_request(actor, key="cash-payment-1"),
        booking_id=booking.public_id,
        amount=booking.total_amount,
        receipt_number="RCPT-1001",
        occurred_at=timezone.now(),
        idempotency_key="cash-payment-1",
    )
    replay = record_office_cash_payment(
        context=context,
        actor=actor,
        request=_request(actor, key="cash-payment-1"),
        booking_id=booking.public_id,
        amount=booking.total_amount,
        receipt_number="RCPT-1001",
        occurred_at=timezone.now(),
        idempotency_key="cash-payment-1",
    )

    booking.refresh_from_db()
    intent = PaymentIntent.objects.get(public_id=first["id"])
    transaction = PaymentTransaction.objects.get(payment_intent=intent)
    entry = LedgerEntry.objects.get(event_id=transaction.id)
    assert first == replay
    assert PaymentTransaction.objects.filter(payment_intent=intent).count() == 1
    assert LedgerEntry.objects.filter(event_id=transaction.id).count() == 1
    assert_entry_balanced(entry)
    assert transaction.receipt_number == "RCPT-1001"
    assert booking.payment_status == Booking.PaymentStatus.PAID
    assert booking.paid_amount == booking.total_amount
    assert AuditLog.objects.filter(action="payment.record_office_cash", object_id=intent.id).count() == 1
    assert Commission.objects.filter(booking=booking, status=Commission.Status.EXPECTED).exists()


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e07_ac02_duplicate_transfer_reference_or_proof_is_rejected() -> None:
    first_booking, first_created = _booking(payment_method="manual_transfer")
    first_intent = create_public_payment_intent(
        pnr=first_booking.pnr,
        manage_token=str(first_created["manage_token"]),
        method_type="manual_transfer",
        return_url=None,
        idempotency_key="manual-intent-1",
    )
    submit_manual_transfer(
        intent_id=str(first_intent["id"]),
        transfer_reference="TRX-DUPLICATE-1",
        transferred_at=timezone.now(),
        amount=first_booking.total_amount,
        sender_reference="محمد",
        proof_file_id="private-proof-object-1",
        idempotency_key="submit-manual-1",
    )

    second_booking, second_created = _booking(payment_method="manual_transfer")
    second_intent = create_public_payment_intent(
        pnr=second_booking.pnr,
        manage_token=str(second_created["manage_token"]),
        method_type="manual_transfer",
        return_url=None,
        idempotency_key="manual-intent-2",
    )
    with pytest.raises(DomainAPIException) as ref_error:
        submit_manual_transfer(
            intent_id=str(second_intent["id"]),
            transfer_reference="TRX-DUPLICATE-1",
            transferred_at=timezone.now(),
            amount=second_booking.total_amount,
            sender_reference="أحمد",
            proof_file_id="private-proof-object-2",
            idempotency_key="submit-manual-duplicate-ref",
        )
    assert ref_error.value.code == "MANUAL_TRANSFER_DUPLICATE"

    with pytest.raises(DomainAPIException) as proof_error:
        submit_manual_transfer(
            intent_id=str(second_intent["id"]),
            transfer_reference="TRX-UNIQUE-2",
            transferred_at=timezone.now(),
            amount=second_booking.total_amount,
            sender_reference="أحمد",
            proof_file_id="private-proof-object-1",
            idempotency_key="submit-manual-duplicate-proof",
        )
    assert proof_error.value.code == "MANUAL_TRANSFER_DUPLICATE"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_manual_transfer_submission_replay_is_idempotent_and_conflicting_reuse_is_rejected() -> None:
    booking, created = _booking(payment_method="manual_transfer")
    intent_payload = create_public_payment_intent(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        method_type="manual_transfer",
        return_url=None,
        idempotency_key="manual-replay-intent",
    )
    transferred_at = timezone.now()
    first = submit_manual_transfer(
        intent_id=str(intent_payload["id"]),
        transfer_reference="TRX-IDEMPOTENT-1",
        transferred_at=transferred_at,
        amount=booking.total_amount,
        sender_reference="محمد",
        proof_file_id="proof-idempotent-1",
        idempotency_key="manual-submit-replay",
    )
    replay = submit_manual_transfer(
        intent_id=str(intent_payload["id"]),
        transfer_reference="TRX-IDEMPOTENT-1",
        transferred_at=transferred_at,
        amount=booking.total_amount,
        sender_reference="محمد",
        proof_file_id="proof-idempotent-1",
        idempotency_key="manual-submit-replay",
    )
    assert first == replay
    assert ManualPaymentSubmission.objects.filter(payment_intent__public_id=intent_payload["id"]).count() == 1

    with pytest.raises(DomainAPIException) as conflict:
        submit_manual_transfer(
            intent_id=str(intent_payload["id"]),
            transfer_reference="TRX-IDEMPOTENT-CHANGED",
            transferred_at=transferred_at,
            amount=booking.total_amount,
            sender_reference="محمد",
            proof_file_id="proof-idempotent-1",
            idempotency_key="manual-submit-replay",
        )
    assert conflict.value.code == "CONFLICT"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e07_ac03_transfer_before_deadline_verified_after_expiry_restores_available_seat() -> None:
    booking, created = _booking(payment_method="manual_transfer")
    intent_payload = create_public_payment_intent(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        method_type="manual_transfer",
        return_url=None,
        idempotency_key="manual-late-review-intent",
    )
    booking.payment_deadline_at = timezone.now() - timedelta(minutes=2)
    booking.save(update_fields=["payment_deadline_at"])
    transferred_at = booking.payment_deadline_at - timedelta(minutes=1)
    submit_manual_transfer(
        intent_id=str(intent_payload["id"]),
        transfer_reference="TRX-BEFORE-DEADLINE",
        transferred_at=transferred_at,
        amount=booking.total_amount,
        sender_reference="محمد",
        proof_file_id="proof-before-deadline",
        idempotency_key="submit-before-deadline",
    )
    assert expire_due_unpaid_bookings(now=timezone.now()) == 1
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.seat_assignments.filter(status=SeatAssignment.Status.RELEASED).count() == 1

    submission = ManualPaymentSubmission.objects.get(transfer_reference="TRX-BEFORE-DEADLINE")
    context, actor = _finance_context(booking)
    verify_manual_payment(
        context=context,
        actor=actor,
        request=_request(actor, key="manual-verify-late"),
        submission_id=str(submission.id),
        decision="verify",
        reason=None,
        idempotency_key="manual-verify-late",
    )
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert booking.payment_status == Booking.PaymentStatus.PAID
    assert booking.seat_assignments.filter(status=SeatAssignment.Status.ACTIVE).count() == 1
    assert booking.tickets.filter(status=Ticket.Status.ACTIVE).count() == 1
    assert not PaymentReconciliationCase.objects.filter(booking=booking).exists()


@override_settings(
    PUBLIC_HOLD_RATE_LIMIT=100,
    PUBLIC_BOOKING_RATE_LIMIT=100,
    ELECTRONIC_PAYMENT_ENABLED=True,
    PAYMENT_WEBHOOK_SECRET="webhook-test-secret",
)
def test_e07_ac04_repeated_success_webhook_records_one_transaction(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created = _booking(payment_method="electronic")
    intent_payload = create_public_payment_intent(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        method_type="electronic",
        return_url="https://example.test/return",
        idempotency_key="electronic-intent-1",
    )
    occurred_at = timezone.now()
    payload = {
        "event_id": "provider-event-once",
        "intent_id": intent_payload["id"],
        "status": "succeeded",
        "amount": str(booking.total_amount),
        "currency": booking.currency,
        "occurred_at": occurred_at.isoformat(),
        "provider_reference": "provider-ref-1",
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"webhook-test-secret", raw, hashlib.sha256).hexdigest()
    first = api_client.post(
        "/v1/webhooks/payments/mock",
        raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE=signature,
    )
    second = api_client.post(
        "/v1/webhooks/payments/mock",
        raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE=signature,
    )
    assert WebhookDelivery.objects.filter(provider_code="mock", provider_event_id="provider-event-once").count() == 1
    assert process_received_webhook_deliveries() == 1
    assert process_received_webhook_deliveries() == 0
    booking.refresh_from_db()
    assert first.status_code == 200
    assert second.status_code == 200
    assert PaymentTransaction.objects.filter(provider_event_id="provider-event-once").count() == 1
    assert LedgerEntry.objects.filter(event_type="ELECTRONIC_PAYMENT_CAPTURED").count() == 1
    assert booking.paid_amount == booking.total_amount
    assert booking.payment_status == Booking.PaymentStatus.PAID


@override_settings(PAYMENT_WEBHOOK_SECRET="webhook-test-secret")
def test_webhook_signature_and_event_hash_are_tamper_evident(api_client) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "event_id": "provider-event-tamper-check",
        "intent_id": "01J00000000000000000000000",
        "status": "succeeded",
        "amount": "10.00",
        "currency": "SYP",
        "occurred_at": timezone.now().isoformat(),
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    invalid = api_client.post(
        "/v1/webhooks/payments/mock",
        raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE="invalid",
    )
    assert invalid.status_code == 400
    assert not WebhookDelivery.objects.filter(provider_event_id=payload["event_id"]).exists()

    valid_signature = hmac.new(b"webhook-test-secret", raw, hashlib.sha256).hexdigest()
    accepted = api_client.post(
        "/v1/webhooks/payments/mock",
        raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE=valid_signature,
    )
    assert accepted.status_code == 200

    changed = {**payload, "amount": "11.00"}
    changed_raw = json.dumps(changed, separators=(",", ":")).encode()
    changed_signature = hmac.new(b"webhook-test-secret", changed_raw, hashlib.sha256).hexdigest()
    collision = api_client.post(
        "/v1/webhooks/payments/mock",
        changed_raw,
        content_type="application/json",
        HTTP_X_PAYMENT_SIGNATURE=changed_signature,
    )
    assert collision.status_code == 400
    assert WebhookDelivery.objects.filter(provider_event_id=payload["event_id"]).count() == 1


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100, ELECTRONIC_PAYMENT_ENABLED=True)
def test_e07_ac05_late_payment_after_seat_resold_does_not_reconfirm_and_opens_reconciliation() -> None:
    booking, created = _booking(payment_method="electronic")
    intent_payload = create_public_payment_intent(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        method_type="electronic",
        return_url=None,
        idempotency_key="electronic-late-intent",
    )
    booking.payment_deadline_at = timezone.now() - timedelta(minutes=5)
    booking.save(update_fields=["payment_deadline_at"])
    original_assignment = booking.seat_assignments.get()
    assert expire_due_unpaid_bookings(now=timezone.now()) == 1

    replacement = Booking.objects.create(
        office=booking.office,
        branch=booking.branch,
        trip=booking.trip,
        source=Booking.Source.OFFICE,
        status=Booking.Status.CONFIRMED,
        payment_status=Booking.PaymentStatus.PAID,
        contact_name="راكب بديل",
        contact_phone="+963944000999",
        currency=booking.currency,
        subtotal_amount=booking.total_amount,
        total_amount=booking.total_amount,
        paid_amount=booking.total_amount,
        policy_snapshot=booking.policy_snapshot,
        pricing_snapshot=booking.pricing_snapshot,
        commission_snapshot={},
        terms_version_ids=booking.terms_version_ids,
        manage_token_hash=uuid.uuid4().bytes,
    )
    passenger = BookingPassenger.objects.create(
        booking=replacement,
        sequence_no=1,
        full_name="راكب بديل",
        gender=BookingPassenger.Gender.MALE,
    )
    SeatAssignment.objects.create(
        trip=booking.trip,
        booking=replacement,
        passenger=passenger,
        trip_seat=original_assignment.trip_seat,
        price_amount=booking.total_amount,
    )

    from payments.services import process_payment_webhook

    process_payment_webhook(
        provider_code="mock",
        payload={
            "event_id": "late-provider-event",
            "intent_id": intent_payload["id"],
            "status": "succeeded",
            "amount": str(booking.total_amount),
            "currency": booking.currency,
            "occurred_at": timezone.now().isoformat(),
            "provider_reference": "late-ref",
        },
    )
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELLED
    assert booking.payment_status == Booking.PaymentStatus.PAID
    case = PaymentReconciliationCase.objects.get(booking=booking)
    assert case.resolution_required == PaymentReconciliationCase.ResolutionRequired.REFUND_OR_ALTERNATIVE
    assert case.reason_code == "payment_after_deadline"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100, ELECTRONIC_PAYMENT_ENABLED=True)
def test_e07_ac06_provider_amount_or_currency_mismatch_does_not_succeed_payment() -> None:
    booking, created = _booking(payment_method="electronic")
    intent_payload = create_public_payment_intent(
        pnr=booking.pnr,
        manage_token=str(created["manage_token"]),
        method_type="electronic",
        return_url=None,
        idempotency_key="electronic-mismatch-intent",
    )
    from payments.services import process_payment_webhook

    process_payment_webhook(
        provider_code="mock",
        payload={
            "event_id": "mismatch-provider-event",
            "intent_id": intent_payload["id"],
            "status": "succeeded",
            "amount": str(booking.total_amount - Decimal("1.00")),
            "currency": "USD",
            "occurred_at": timezone.now().isoformat(),
        },
    )
    booking.refresh_from_db()
    intent = PaymentIntent.objects.get(public_id=intent_payload["id"])
    assert intent.status == PaymentIntent.Status.PENDING_VERIFICATION
    assert booking.payment_status == Booking.PaymentStatus.UNPAID
    assert booking.paid_amount == 0
    failed = PaymentTransaction.objects.get(payment_intent=intent)
    assert failed.status == PaymentTransaction.Status.FAILED
    case = PaymentReconciliationCase.objects.get(payment_intent=intent)
    assert case.reason_code == "payment_amount_currency_mismatch"


@pytest.mark.postgresql  # type: ignore[misc]
def test_postgresql_rejects_unbalanced_ledger_entry_at_commit() -> None:
    from django.db import IntegrityError, connection, transaction

    from finance.models import LedgerAccount, LedgerEntry, LedgerPosting

    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL deferred constraint trigger required")
    booking, _ = _booking(payment_method="office_cash")
    account = LedgerAccount.objects.create(
        code=f"test-unbalanced-{uuid.uuid4()}",
        account_type=LedgerAccount.AccountType.ASSET,
        currency=booking.currency,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        entry = LedgerEntry.objects.create(
            event_type="TEST_UNBALANCED",
            event_id=uuid.uuid4(),
            booking=booking,
            trip=booking.trip,
            office=booking.office,
            currency=booking.currency,
            occurred_at=timezone.now(),
        )
        LedgerPosting.objects.create(
            entry=entry,
            account=account,
            direction=LedgerPosting.Direction.DEBIT,
            amount=Decimal("1.00"),
        )
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS trg_ledger_balance IMMEDIATE")
