from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, SeatAssignment
from bookings.services import manage_token_matches
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey, OutboxEvent
from finance.services import money, post_direct_payment_entry, post_electronic_capture_entry
from identity.models import User
from organizations.services import OfficeContext
from payments.models import (
    ManualPaymentSubmission,
    PaymentIntent,
    PaymentReconciliationCase,
    PaymentTransaction,
    WebhookDelivery,
)
from tickets.services import issue_tickets_for_booking


def _outstanding_amount(booking: Booking) -> Decimal:
    return money(booking.total_amount - booking.paid_amount)


def _serialize_intent(intent: PaymentIntent) -> dict[str, Any]:
    return {
        "id": intent.public_id,
        "method_type": intent.method_type,
        "status": intent.status,
        "amount": str(intent.amount),
        "currency": intent.currency,
        "provider_action": intent.provider_action,
        "expires_at": intent.expires_at,
    }


def _booking_for_public_management(*, pnr: str, manage_token: str) -> Booking:
    booking = Booking.objects.select_related("trip", "office", "branch").filter(pnr=pnr.strip().upper()).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return booking


def _available_methods(booking: Booking) -> list[str]:
    methods = booking.trip.pricing_snapshot.get("payment_methods", [])
    return [str(value) for value in methods]


@transaction.atomic
def create_public_payment_intent(
    *,
    pnr: str,
    manage_token: str,
    method_type: str,
    return_url: str | None,
    idempotency_key: str,
) -> dict[str, Any]:
    booking = _booking_for_public_management(pnr=pnr, manage_token=manage_token)
    booking = Booking.objects.select_for_update().select_related("trip").get(id=booking.id)
    if booking.payment_status in {Booking.PaymentStatus.PAID, Booking.PaymentStatus.REFUNDED}:
        raise DomainAPIException("PAYMENT_ALREADY_SUCCEEDED")
    if method_type not in _available_methods(booking):
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "method_type", "reason": "not_available_for_booking"}],
        )
    existing = PaymentIntent.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.method_type != method_type:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        return _serialize_intent(existing)

    amount = _outstanding_amount(booking)
    if amount <= 0:
        raise DomainAPIException("PAYMENT_ALREADY_SUCCEEDED")
    status = PaymentIntent.Status.CREATED
    provider_code: str | None = None
    action: dict[str, Any] | None = None
    if method_type == PaymentIntent.MethodType.MANUAL_TRANSFER:
        action = {
            "type": "manual_transfer",
            "instructions": booking.policy_snapshot.get("payment_instructions", "حوّل المبلغ وارفع المرجع والإثبات."),
        }
    elif method_type == PaymentIntent.MethodType.ELECTRONIC:
        if not settings.ELECTRONIC_PAYMENT_ENABLED:
            raise DomainAPIException("PAYMENT_PROVIDER_UNAVAILABLE")
        status = PaymentIntent.Status.REQUIRES_ACTION
        provider_code = settings.DEFAULT_PAYMENT_PROVIDER_CODE
        action = {
            "type": "redirect",
            "url": f"{settings.PAYMENT_PROVIDER_CHECKOUT_BASE_URL.rstrip('/')}/{booking.public_id}",
            "return_url": return_url,
        }
    elif method_type == PaymentIntent.MethodType.OFFICE_CASH:
        action = {
            "type": "office_cash",
            "branch_id": booking.branch.public_id,
            "deadline_at": booking.payment_deadline_at,
        }

    intent = PaymentIntent.objects.create(
        booking=booking,
        method_type=method_type,
        status=status,
        amount=amount,
        currency=booking.currency,
        provider_code=provider_code,
        provider_action=action,
        idempotency_key=idempotency_key,
        expires_at=booking.payment_deadline_at,
    )
    OutboxEvent.objects.create(
        aggregate_type="payment_intent",
        aggregate_id=intent.id,
        event_type="payment.intent.created",
        payload={"intent_id": intent.public_id, "booking_id": booking.public_id, "method": method_type},
    )
    return _serialize_intent(intent)


def _proof_hash(proof_file_id: str | None) -> str | None:
    if not proof_file_id:
        return None
    return hashlib.sha256(proof_file_id.strip().encode()).hexdigest()


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def submit_manual_transfer(
    *,
    intent_id: str,
    transfer_reference: str,
    transferred_at: datetime,
    amount: Decimal,
    sender_reference: str | None,
    proof_file_id: str | None,
    idempotency_key: str,
) -> dict[str, Any]:
    intent = PaymentIntent.objects.select_for_update().select_related("booking").filter(public_id=intent_id).first()
    if intent is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    fingerprint = _payload_hash(
        {
            "transfer_reference": transfer_reference.strip(),
            "transferred_at": transferred_at,
            "amount": money(amount),
            "sender_reference": sender_reference.strip() if sender_reference else None,
            "proof_file_id": proof_file_id.strip() if proof_file_id else None,
        }
    )
    replay = (
        IdempotencyKey.objects.select_for_update()
        .filter(scope_type="manual_transfer", scope_id=intent.id, key=idempotency_key)
        .first()
    )
    if replay is not None:
        if replay.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        return _serialize_intent(intent)
    idempotency = IdempotencyKey.objects.create(
        scope_type="manual_transfer",
        scope_id=intent.id,
        key=idempotency_key,
        request_hash=fingerprint,
        locked_until=timezone.now() + timedelta(seconds=30),
        expires_at=timezone.now() + timedelta(hours=24),
    )
    if intent.method_type != PaymentIntent.MethodType.MANUAL_TRANSFER or intent.status not in {
        PaymentIntent.Status.CREATED,
        PaymentIntent.Status.REQUIRES_ACTION,
    }:
        raise DomainAPIException("PAYMENT_STATE_CONFLICT")
    normalized_reference = transfer_reference.strip()
    digest = _proof_hash(proof_file_id)
    if ManualPaymentSubmission.objects.filter(
        Q(transfer_reference=normalized_reference) | (Q(proof_sha256=digest) if digest else Q(pk__isnull=True))
    ).exists():
        raise DomainAPIException("MANUAL_TRANSFER_DUPLICATE")
    if money(amount) != money(intent.amount):
        raise DomainAPIException("PAYMENT_AMOUNT_MISMATCH")
    try:
        ManualPaymentSubmission.objects.create(
            payment_intent=intent,
            sender_reference=sender_reference.strip() if sender_reference else None,
            transfer_reference=normalized_reference,
            transferred_at=transferred_at,
            amount=money(amount),
            proof_object_key=proof_file_id,
            proof_sha256=digest,
        )
    except IntegrityError as exc:
        raise DomainAPIException("MANUAL_TRANSFER_DUPLICATE") from exc
    intent.status = PaymentIntent.Status.PENDING_VERIFICATION
    intent.save(update_fields=["status", "updated_at"])
    booking = intent.booking
    booking.payment_status = Booking.PaymentStatus.PENDING_VERIFICATION
    booking.save(update_fields=["payment_status", "updated_at"])
    OutboxEvent.objects.create(
        aggregate_type="payment_intent",
        aggregate_id=intent.id,
        event_type="payment.manual_transfer.submitted",
        payload={"intent_id": intent.public_id, "booking_id": booking.public_id},
    )
    response = _serialize_intent(intent)
    idempotency.response_status = 200
    idempotency.response_body = json.loads(json.dumps(response, default=str))
    idempotency.locked_until = None
    idempotency.save(update_fields=["response_status", "response_body", "locked_until"])
    return response


def _active_inventory_complete(booking: Booking) -> bool:
    passenger_count = booking.passengers.count()
    active_count = booking.seat_assignments.filter(status=SeatAssignment.Status.ACTIVE).count()
    return passenger_count > 0 and active_count == passenger_count


def _try_restore_inventory(booking: Booking) -> bool:
    assignments = list(
        SeatAssignment.objects.select_for_update().select_related("trip_seat").filter(booking=booking).order_by("id")
    )
    if not assignments or len(assignments) != booking.passengers.count():
        return False
    seat_ids = [assignment.trip_seat_id for assignment in assignments]
    conflicts = SeatAssignment.objects.filter(
        trip=booking.trip,
        trip_seat_id__in=seat_ids,
        status=SeatAssignment.Status.ACTIVE,
    ).exclude(booking=booking)
    if conflicts.exists() or any(not assignment.trip_seat.sellable for assignment in assignments):
        return False
    SeatAssignment.objects.filter(id__in=[item.id for item in assignments]).update(
        status=SeatAssignment.Status.ACTIVE,
        released_at=None,
    )
    return True


def _open_reconciliation(
    *,
    intent: PaymentIntent,
    reason_code: str,
    received_amount: Decimal,
    received_currency: str,
    resolution_required: str,
    metadata: dict[str, Any] | None = None,
) -> PaymentReconciliationCase:
    case, created = PaymentReconciliationCase.objects.get_or_create(
        payment_intent=intent,
        reason_code=reason_code,
        status=PaymentReconciliationCase.Status.OPEN,
        defaults={
            "booking": intent.booking,
            "resolution_required": resolution_required,
            "expected_amount": intent.amount,
            "received_amount": money(received_amount),
            "expected_currency": intent.currency,
            "received_currency": received_currency,
            "metadata": metadata or {},
        },
    )
    if not created and metadata:
        case.metadata = {**case.metadata, **metadata}
        case.save(update_fields=["metadata"])
    if created:
        OutboxEvent.objects.create(
            aggregate_type="payment_reconciliation",
            aggregate_id=case.id,
            event_type="payment.reconciliation_required",
            payload={
                "case_id": str(case.id),
                "booking_id": intent.booking.public_id,
                "reason_code": reason_code,
                "resolution_required": resolution_required,
            },
        )
    return case


def _complete_booking_after_payment(
    *,
    intent: PaymentIntent,
    transaction: PaymentTransaction,
    payment_occurred_at: datetime,
) -> bool:
    booking = Booking.objects.select_for_update().select_related("trip").get(id=intent.booking_id)
    deadline = booking.payment_deadline_at
    paid_within_deadline = deadline is None or payment_occurred_at <= deadline
    inventory_ok = _active_inventory_complete(booking)
    if not inventory_ok and paid_within_deadline:
        inventory_ok = _try_restore_inventory(booking)

    booking.paid_amount = money(booking.paid_amount + transaction.amount)
    booking.payment_status = (
        Booking.PaymentStatus.PAID
        if booking.paid_amount >= booking.total_amount
        else Booking.PaymentStatus.PARTIALLY_PAID
    )

    can_confirm = booking.payment_status == Booking.PaymentStatus.PAID and paid_within_deadline and inventory_ok
    if can_confirm:
        booking.status = Booking.Status.CONFIRMED
        booking.confirmed_at = booking.confirmed_at or timezone.now()
        booking.cancelled_at = None
    booking.save(
        update_fields=[
            "paid_amount",
            "payment_status",
            "status",
            "confirmed_at",
            "cancelled_at",
            "updated_at",
        ]
    )
    if can_confirm:
        issue_tickets_for_booking(booking)
        OutboxEvent.objects.create(
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type="payment.confirmed",
            payload={"booking_id": booking.public_id, "intent_id": intent.public_id},
        )
        return True

    reason = "payment_after_deadline" if not paid_within_deadline else "payment_inventory_unavailable"
    _open_reconciliation(
        intent=intent,
        reason_code=reason,
        received_amount=transaction.amount,
        received_currency=transaction.currency,
        resolution_required=PaymentReconciliationCase.ResolutionRequired.REFUND_OR_ALTERNATIVE,
        metadata={"transaction_id": str(transaction.id)},
    )
    return False


def _create_transaction_once(
    *,
    intent: PaymentIntent,
    transaction_type: str,
    amount: Decimal,
    currency: str,
    occurred_at: datetime,
    provider_event_id: str | None,
    receipt_number: str | None,
    reference: str,
) -> tuple[PaymentTransaction, bool]:
    if provider_event_id:
        existing = PaymentTransaction.objects.filter(provider_event_id=provider_event_id).first()
        if existing is not None:
            return existing, False
    digest = hashlib.sha256(reference.encode()).digest()
    existing_hash = PaymentTransaction.objects.filter(raw_reference_hash=digest).first()
    if existing_hash is not None:
        return existing_hash, False
    try:
        transaction_row = PaymentTransaction.objects.create(
            payment_intent=intent,
            transaction_type=transaction_type,
            status=PaymentTransaction.Status.SUCCEEDED,
            amount=money(amount),
            currency=currency,
            provider_event_id=provider_event_id,
            receipt_number=receipt_number,
            occurred_at=occurred_at,
            raw_reference_hash=digest,
        )
    except IntegrityError:
        existing = PaymentTransaction.objects.filter(
            Q(provider_event_id=provider_event_id) | Q(raw_reference_hash=digest)
        ).first()
        if existing is None:
            raise
        return existing, False
    return transaction_row, True


@transaction.atomic
def record_office_cash_payment(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    booking_id: str,
    amount: Decimal,
    receipt_number: str,
    occurred_at: datetime | None,
    idempotency_key: str,
) -> dict[str, Any]:
    booking = (
        Booking.objects.select_for_update()
        .select_related("trip", "office")
        .filter(public_id=booking_id, office=context.office)
        .first()
    )
    if booking is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    existing_intent = PaymentIntent.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
    if existing_intent is not None:
        return _serialize_intent(existing_intent)
    if booking.payment_status == Booking.PaymentStatus.PAID:
        raise DomainAPIException("PAYMENT_ALREADY_SUCCEEDED")
    expected = _outstanding_amount(booking)
    if money(amount) != expected:
        raise DomainAPIException("PAYMENT_AMOUNT_MISMATCH")
    event_time = occurred_at or timezone.now()
    intent = PaymentIntent.objects.create(
        booking=booking,
        method_type=PaymentIntent.MethodType.OFFICE_CASH,
        status=PaymentIntent.Status.CREATED,
        amount=expected,
        currency=booking.currency,
        idempotency_key=idempotency_key,
        expires_at=booking.payment_deadline_at,
        created_by=actor,
    )
    transaction_row, created = _create_transaction_once(
        intent=intent,
        transaction_type=PaymentTransaction.TransactionType.PAYMENT,
        amount=expected,
        currency=booking.currency,
        occurred_at=event_time,
        provider_event_id=f"cash:{context.office.id}:{receipt_number.strip()}",
        receipt_number=receipt_number.strip(),
        reference=f"cash:{context.office.id}:{receipt_number.strip()}",
    )
    if created:
        post_direct_payment_entry(
            transaction_id=transaction_row.id,
            booking=booking,
            amount=transaction_row.amount,
            occurred_at=event_time,
        )
        _complete_booking_after_payment(intent=intent, transaction=transaction_row, payment_occurred_at=event_time)
        record_audit(
            action="payment.record_office_cash",
            object_type="payment_intent",
            actor_user=actor,
            office_id=context.office.id,
            object_id=intent.id,
            request=request,
            after={
                "booking_id": booking.public_id,
                "amount": str(expected),
                "currency": booking.currency,
                "receipt_number": receipt_number.strip(),
            },
        )
    intent.status = PaymentIntent.Status.SUCCEEDED
    intent.provider_reference = receipt_number.strip()
    intent.provider_action = {"receipt_number": receipt_number.strip()}
    intent.save(update_fields=["status", "provider_reference", "provider_action", "updated_at"])
    return _serialize_intent(intent)


@transaction.atomic
def verify_manual_payment(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    submission_id: str,
    decision: str,
    reason: str | None,
    idempotency_key: str,
) -> dict[str, Any]:
    _ = idempotency_key
    submission = (
        ManualPaymentSubmission.objects.select_for_update()
        .select_related("payment_intent__booking__office", "payment_intent__booking__trip")
        .filter(id=submission_id, payment_intent__booking__office=context.office)
        .first()
    )
    if submission is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    intent = submission.payment_intent
    if submission.status in {ManualPaymentSubmission.Status.VERIFIED, ManualPaymentSubmission.Status.REJECTED}:
        return _serialize_intent(intent)
    if intent.created_by_id == actor.id:
        raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
    if decision == "reject":
        if not reason or not reason.strip():
            raise DomainAPIException("PAYMENT_REJECTION_REASON_REQUIRED")
        submission.status = ManualPaymentSubmission.Status.REJECTED
        submission.reviewed_by = actor
        submission.reviewed_at = timezone.now()
        submission.rejection_reason = reason.strip()
        submission.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])
        intent.status = PaymentIntent.Status.FAILED
        intent.save(update_fields=["status", "updated_at"])
        intent.booking.payment_status = Booking.PaymentStatus.UNPAID
        intent.booking.save(update_fields=["payment_status", "updated_at"])
        record_audit(
            action="payment.manual_transfer.reject",
            object_type="manual_payment_submission",
            actor_user=actor,
            office_id=context.office.id,
            object_id=submission.id,
            request=request,
            reason_code=reason.strip(),
        )
        return _serialize_intent(intent)
    if decision != "verify":
        raise DomainAPIException("VALIDATION_ERROR")
    if money(submission.amount) != money(intent.amount):
        raise DomainAPIException("PAYMENT_AMOUNT_MISMATCH")

    transaction_row, created = _create_transaction_once(
        intent=intent,
        transaction_type=PaymentTransaction.TransactionType.PAYMENT,
        amount=submission.amount,
        currency=intent.currency,
        occurred_at=submission.transferred_at,
        provider_event_id=f"manual:{submission.transfer_reference}",
        receipt_number=submission.transfer_reference,
        reference=f"manual:{submission.transfer_reference}",
    )
    if created:
        post_direct_payment_entry(
            transaction_id=transaction_row.id,
            booking=intent.booking,
            amount=transaction_row.amount,
            occurred_at=submission.transferred_at,
        )
        _complete_booking_after_payment(
            intent=intent,
            transaction=transaction_row,
            payment_occurred_at=submission.transferred_at,
        )
    submission.status = ManualPaymentSubmission.Status.VERIFIED
    submission.reviewed_by = actor
    submission.reviewed_at = timezone.now()
    submission.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    intent.status = PaymentIntent.Status.SUCCEEDED
    intent.provider_reference = submission.transfer_reference
    intent.save(update_fields=["status", "provider_reference", "updated_at"])
    record_audit(
        action="payment.manual_transfer.verify",
        object_type="manual_payment_submission",
        actor_user=actor,
        office_id=context.office.id,
        object_id=submission.id,
        request=request,
        after={"booking_id": intent.booking.public_id, "amount": str(submission.amount)},
    )
    return _serialize_intent(intent)


def list_manual_payment_queue(*, context: OfficeContext) -> list[dict[str, Any]]:
    submissions = (
        ManualPaymentSubmission.objects.select_related("payment_intent__booking")
        .filter(payment_intent__booking__office=context.office)
        .order_by("-submitted_at")[:100]
    )
    return [
        {
            "id": str(item.id),
            "booking_id": item.payment_intent.booking.public_id,
            "pnr": item.payment_intent.booking.pnr,
            "transfer_reference": item.transfer_reference,
            "sender_reference": item.sender_reference,
            "transferred_at": item.transferred_at,
            "amount": str(item.amount),
            "currency": item.payment_intent.currency,
            "proof_file_id": item.proof_object_key,
            "status": item.status,
            "submitted_at": item.submitted_at,
        }
        for item in submissions
    ]


@transaction.atomic
def receive_payment_webhook(
    *,
    provider_code: str,
    payload: dict[str, Any],
    raw_payload: bytes,
) -> WebhookDelivery:
    event_id = str(payload.get("event_id", "")).strip()
    event_status = str(payload.get("status", "")).strip()
    if not event_id or not event_status:
        raise DomainAPIException("PAYMENT_WEBHOOK_INVALID")
    payload_hash = hashlib.sha256(raw_payload).hexdigest()
    normalized_payload = json.loads(json.dumps(payload, default=str))
    delivery, created = WebhookDelivery.objects.get_or_create(
        provider_code=provider_code,
        provider_event_id=event_id,
        defaults={
            "event_type": f"payment.{event_status}",
            "signature_valid": True,
            "payload_hash": payload_hash,
            "normalized_payload": normalized_payload,
        },
    )
    if not created and delivery.payload_hash != payload_hash:
        raise DomainAPIException("PAYMENT_WEBHOOK_INVALID")
    if created:
        OutboxEvent.objects.create(
            aggregate_type="webhook_delivery",
            aggregate_id=delivery.id,
            event_type="payment.webhook.received",
            payload={
                "delivery_id": str(delivery.id),
                "provider_code": provider_code,
                "provider_event_id": event_id,
            },
        )
    return delivery


@transaction.atomic
def process_webhook_delivery(*, delivery_id: uuid.UUID) -> bool:
    delivery = WebhookDelivery.objects.select_for_update().filter(id=delivery_id).first()
    if delivery is None:
        return False
    if delivery.status == WebhookDelivery.Status.PROCESSED:
        return False
    try:
        process_payment_webhook(
            provider_code=delivery.provider_code,
            payload=delivery.normalized_payload,
        )
    except DomainAPIException as exc:
        delivery.status = WebhookDelivery.Status.FAILED
        delivery.error_code = exc.code
        delivery.processed_at = timezone.now()
        delivery.save(update_fields=["status", "error_code", "processed_at"])
        return False
    delivery.status = WebhookDelivery.Status.PROCESSED
    delivery.error_code = None
    delivery.processed_at = timezone.now()
    delivery.save(update_fields=["status", "error_code", "processed_at"])
    return True


def process_received_webhook_deliveries(*, limit: int = 100) -> int:
    delivery_ids = list(
        WebhookDelivery.objects.filter(status=WebhookDelivery.Status.RECEIVED)
        .order_by("received_at")
        .values_list("id", flat=True)[:limit]
    )
    processed = 0
    for delivery_id in delivery_ids:
        if process_webhook_delivery(delivery_id=delivery_id):
            processed += 1
    return processed


def _provider_signature(payload_bytes: bytes) -> str:
    return hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()


def webhook_signature_valid(*, payload_bytes: bytes, signature: str) -> bool:
    return bool(signature) and hmac.compare_digest(_provider_signature(payload_bytes), signature.strip())


def _record_failed_provider_event(
    *,
    intent: PaymentIntent,
    event_id: str,
    amount: Decimal,
    currency: str,
    occurred_at: datetime,
    provider_code: str,
) -> PaymentTransaction:
    digest = hashlib.sha256(f"provider:{provider_code}:{event_id}".encode()).digest()
    transaction_row, _ = PaymentTransaction.objects.get_or_create(
        provider_event_id=event_id,
        defaults={
            "payment_intent": intent,
            "transaction_type": PaymentTransaction.TransactionType.CAPTURE,
            "status": PaymentTransaction.Status.FAILED,
            "amount": money(amount),
            "currency": currency,
            "occurred_at": occurred_at,
            "raw_reference_hash": digest,
        },
    )
    return transaction_row


@transaction.atomic
def process_payment_webhook(*, provider_code: str, payload: dict[str, Any]) -> dict[str, bool]:
    event_id = str(payload.get("event_id", "")).strip()
    intent_id = str(payload.get("intent_id", "")).strip()
    event_status = str(payload.get("status", "")).strip()
    if not event_id or not intent_id or event_status != "succeeded":
        raise DomainAPIException("PAYMENT_WEBHOOK_INVALID")
    existing = PaymentTransaction.objects.filter(provider_event_id=event_id).first()
    if existing is not None:
        return {"received": True}
    intent = (
        PaymentIntent.objects.select_for_update()
        .select_related("booking__trip", "booking__office")
        .filter(public_id=intent_id, provider_code=provider_code)
        .first()
    )
    if intent is None or intent.method_type != PaymentIntent.MethodType.ELECTRONIC:
        raise DomainAPIException("PAYMENT_WEBHOOK_INVALID")
    try:
        amount = money(Decimal(str(payload["amount"])))
        currency = str(payload["currency"]).upper()
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise DomainAPIException("PAYMENT_WEBHOOK_INVALID") from exc
    if timezone.is_naive(occurred_at):
        occurred_at = timezone.make_aware(occurred_at)

    if amount != money(intent.amount) or currency != intent.currency:
        failed_transaction = _record_failed_provider_event(
            intent=intent,
            event_id=event_id,
            amount=amount,
            currency=currency,
            occurred_at=occurred_at,
            provider_code=provider_code,
        )
        intent.status = PaymentIntent.Status.PENDING_VERIFICATION
        intent.save(update_fields=["status", "updated_at"])
        _open_reconciliation(
            intent=intent,
            reason_code="payment_amount_currency_mismatch",
            received_amount=amount,
            received_currency=currency,
            resolution_required=PaymentReconciliationCase.ResolutionRequired.AMOUNT_CURRENCY_REVIEW,
            metadata={"provider_event_id": event_id, "transaction_id": str(failed_transaction.id)},
        )
        return {"received": True}

    transaction_row, created = _create_transaction_once(
        intent=intent,
        transaction_type=PaymentTransaction.TransactionType.CAPTURE,
        amount=amount,
        currency=currency,
        occurred_at=occurred_at,
        provider_event_id=event_id,
        receipt_number=str(payload.get("provider_reference") or event_id),
        reference=f"provider:{provider_code}:{event_id}",
    )
    if created:
        post_electronic_capture_entry(
            transaction_id=transaction_row.id,
            booking=intent.booking,
            amount=transaction_row.amount,
            occurred_at=occurred_at,
        )
        _complete_booking_after_payment(
            intent=intent,
            transaction=transaction_row,
            payment_occurred_at=occurred_at,
        )
    intent.status = PaymentIntent.Status.SUCCEEDED
    intent.provider_reference = str(payload.get("provider_reference") or event_id)
    intent.save(update_fields=["status", "provider_reference", "updated_at"])
    return {"received": True}


@transaction.atomic
def expire_due_unpaid_bookings(*, now: datetime | None = None) -> int:
    current = now or timezone.now()
    bookings = list(
        Booking.objects.select_for_update()
        .filter(
            status=Booking.Status.AWAITING_PAYMENT,
            payment_deadline_at__lt=current,
            paid_amount__lt=models.F("total_amount"),
        )
        .order_by("id")
    )
    expired = 0
    for booking in bookings:
        if PaymentTransaction.objects.filter(
            payment_intent__booking=booking,
            status=PaymentTransaction.Status.SUCCEEDED,
            occurred_at__lte=booking.payment_deadline_at,
        ).exists():
            continue
        SeatAssignment.objects.filter(
            booking=booking,
            status=SeatAssignment.Status.ACTIVE,
        ).update(status=SeatAssignment.Status.RELEASED, released_at=current)
        PaymentIntent.objects.filter(
            booking=booking,
            status__in=[PaymentIntent.Status.CREATED, PaymentIntent.Status.REQUIRES_ACTION],
        ).update(status=PaymentIntent.Status.EXPIRED)
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = current
        booking.save(update_fields=["status", "cancelled_at", "updated_at"])
        OutboxEvent.objects.create(
            aggregate_type="booking",
            aggregate_id=booking.id,
            event_type="booking.payment_deadline_expired",
            payload={"booking_id": booking.public_id, "pnr": booking.pnr},
        )
        expired += 1
    return expired
