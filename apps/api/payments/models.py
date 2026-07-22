from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class PaymentIntent(UUIDPrimaryKeyModel):
    class MethodType(models.TextChoices):
        OFFICE_CASH = "office_cash", "Office cash"
        MANUAL_TRANSFER = "manual_transfer", "Manual transfer"
        ELECTRONIC = "electronic", "Electronic"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        REQUIRES_ACTION = "requires_action", "Requires action"
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="payment_intents",
    )
    method_type = models.CharField(max_length=24, choices=MethodType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    provider_code = models.CharField(max_length=60, null=True, blank=True)
    provider_reference = models.CharField(max_length=160, null=True, blank=True)
    idempotency_key = models.CharField(max_length=120)
    provider_action = models.JSONField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="created_payment_intents",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_intents"
        constraints = [
            models.UniqueConstraint(fields=["booking", "idempotency_key"], name="uq_booking_payment_intent_key"),
            models.UniqueConstraint(
                fields=["provider_code", "provider_reference"],
                condition=Q(provider_reference__isnull=False),
                name="uq_payment_provider_reference",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="ck_payment_intent_amount"),
        ]
        indexes = [
            models.Index(fields=["booking", "status"], name="ix_pay_intent_booking_status"),
            models.Index(fields=["expires_at", "status"], name="ix_pay_intent_expiry"),
        ]


class PaymentTransaction(UUIDPrimaryKeyModel):
    class TransactionType(models.TextChoices):
        AUTHORIZE = "authorize", "Authorize"
        CAPTURE = "capture", "Capture"
        PAYMENT = "payment", "Payment"
        REVERSAL = "reversal", "Reversal"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REVERSED = "reversed", "Reversed"

    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.RESTRICT,
        related_name="transactions",
    )
    transaction_type = models.CharField(max_length=24, choices=TransactionType.choices)
    status = models.CharField(max_length=20, choices=Status.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    provider_event_id = models.CharField(max_length=160, null=True, blank=True, unique=True)
    receipt_number = models.CharField(max_length=120, null=True, blank=True)
    occurred_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    raw_reference_hash = models.BinaryField(null=True, blank=True, unique=True)

    class Meta:
        db_table = "payment_transactions"
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_payment_tx_amount")]
        indexes = [models.Index(fields=["payment_intent", "status"], name="ix_pay_tx_intent_status")]


class ManualPaymentSubmission(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        DUPLICATE = "duplicate", "Duplicate"

    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.RESTRICT,
        related_name="manual_submissions",
    )
    sender_reference = models.CharField(max_length=160, null=True, blank=True)
    transfer_reference = models.CharField(max_length=160, unique=True)
    transferred_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    proof_object_key = models.TextField(null=True, blank=True)
    proof_sha256 = models.CharField(max_length=64, null=True, blank=True, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="reviewed_manual_payments",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "manual_payment_submissions"
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_manual_payment_amount")]
        indexes = [models.Index(fields=["status", "submitted_at"], name="ix_manual_pay_review_queue")]


class WebhookDelivery(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider_code = models.CharField(max_length=60)
    provider_event_id = models.CharField(max_length=160)
    event_type = models.CharField(max_length=120)
    signature_valid = models.BooleanField()
    payload_hash = models.CharField(max_length=64)
    normalized_payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        db_table = "webhook_deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["provider_code", "provider_event_id"],
                name="uq_webhook_provider_event",
            )
        ]
        indexes = [models.Index(fields=["status", "received_at"], name="ix_webhook_delivery_queue")]


class PaymentReconciliationCase(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    class ResolutionRequired(models.TextChoices):
        REFUND_OR_ALTERNATIVE = "refund_or_alternative", "Refund or alternative"
        AMOUNT_CURRENCY_REVIEW = "amount_currency_review", "Amount/currency review"
        OVERPAYMENT_REFUND = "overpayment_refund", "Overpayment refund"

    payment_intent = models.ForeignKey(
        PaymentIntent,
        on_delete=models.RESTRICT,
        related_name="reconciliation_cases",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="payment_reconciliation_cases",
    )
    reason_code = models.CharField(max_length=80)
    resolution_required = models.CharField(max_length=40, choices=ResolutionRequired.choices)
    expected_amount = models.DecimalField(max_digits=18, decimal_places=2)
    received_amount = models.DecimalField(max_digits=18, decimal_places=2)
    expected_currency = models.CharField(max_length=3)
    received_currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payment_reconciliation_cases"
        constraints = [
            models.UniqueConstraint(
                fields=["payment_intent", "reason_code"],
                condition=Q(status="open"),
                name="uq_open_reconciliation_reason",
            )
        ]
        indexes = [models.Index(fields=["status", "reason_code"], name="ix_pay_recon_queue")]


class Refund(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="refunds",
    )
    passenger = models.ForeignKey(
        "bookings.BookingPassenger",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="refunds",
    )
    payment_intent = models.ForeignKey(
        PaymentIntent,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="refunds",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.REQUESTED)
    reason_code = models.CharField(max_length=80)
    requested_amount = models.DecimalField(max_digits=18, decimal_places=2)
    approved_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="requested_refunds",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_refunds",
    )
    provider_reference = models.CharField(max_length=160, null=True, blank=True)
    quote_snapshot = models.JSONField(default=dict)
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "refunds"
        constraints = [
            models.CheckConstraint(condition=Q(requested_amount__gt=0), name="ck_refund_requested_positive"),
            models.CheckConstraint(
                condition=Q(approved_amount__isnull=True)
                | (Q(approved_amount__gte=0) & Q(approved_amount__lte=models.F("requested_amount"))),
                name="ck_refund_approved_range",
            ),
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True) | ~Q(approved_by=models.F("requested_by")),
                name="ck_refund_dual_approval",
            ),
            models.UniqueConstraint(
                fields=["booking", "passenger"],
                condition=Q(status__in=["requested", "under_review", "approved", "processing"]),
                name="uq_open_refund_booking_passenger",
            ),
        ]
        indexes = [
            models.Index(fields=["booking", "status"], name="ix_refund_booking_status"),
            models.Index(fields=["status", "created_at"], name="ix_refund_review_queue"),
        ]


class Chargeback(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        EVIDENCE_SUBMITTED = "evidence_submitted", "Evidence submitted"
        WON = "won", "Won"
        LOST = "lost", "Lost"
        ACCEPTED = "accepted", "Accepted"
        CLOSED = "closed", "Closed"

    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.RESTRICT,
        related_name="chargebacks",
    )
    provider_case_id = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    deadline_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "chargebacks"
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_chargeback_amount")]
        indexes = [models.Index(fields=["status", "deadline_at"], name="ix_chargeback_status_deadline")]
