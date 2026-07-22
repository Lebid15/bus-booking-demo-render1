from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class SubscriptionPlan(UUIDPrimaryKeyModel):
    class BillingPeriod(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        YEARLY = "yearly", "Yearly"
        CUSTOM = "custom", "Custom"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    code = models.CharField(max_length=80, unique=True)
    name_ar = models.CharField(max_length=160)
    billing_period = models.CharField(max_length=20, choices=BillingPeriod.choices)
    price_amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    features_json = models.JSONField(default=dict)
    limits_json = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="created_subscription_plans",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription_plans"
        constraints = [
            models.CheckConstraint(condition=Q(price_amount__gte=0), name="ck_subscription_plan_price_nonnegative"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gt=models.F("effective_from")),
                name="ck_subscription_plan_effective_window",
            ),
        ]
        indexes = [models.Index(fields=["status", "effective_from"], name="ix_subscription_plan_active")]


class OfficeSubscription(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        GRACE = "grace", "Grace"
        SUSPENDED = "suspended", "Suspended"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    ACTIVEISH_STATUSES = (Status.TRIAL, Status.ACTIVE, Status.PAST_DUE, Status.GRACE)

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="subscriptions")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.RESTRICT, related_name="office_subscriptions")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ACTIVE)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    price_snapshot = models.JSONField()
    features_snapshot = models.JSONField(default=dict)
    limits_snapshot = models.JSONField(default=dict)
    auto_renew = models.BooleanField(default=False)
    cancel_at_period_end = models.BooleanField(default=False)
    source = models.CharField(max_length=24, default="platform")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "office_subscriptions"
        constraints = [
            models.CheckConstraint(condition=Q(period_end__gt=models.F("period_start")), name="ck_subscription_period"),
            models.UniqueConstraint(
                fields=["office"],
                condition=Q(status__in=["trial", "active", "past_due", "grace"]),
                name="uq_active_subscription",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "status", "period_end"], name="ix_office_subscription_current"),
            models.Index(fields=["status", "period_end"], name="ix_subscription_due"),
        ]


class SubscriptionInvoice(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OPEN = "open", "Open"
        PAID = "paid", "Paid"
        VOID = "void", "Void"
        UNCOLLECTIBLE = "uncollectible", "Uncollectible"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    office_subscription = models.ForeignKey(
        OfficeSubscription, on_delete=models.RESTRICT, related_name="invoices"
    )
    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="subscription_invoices")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    currency = models.CharField(max_length=3)
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    ledger_entry = models.ForeignKey(
        "finance.LedgerEntry",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="subscription_invoice_entries",
    )
    payment_ledger_entry = models.ForeignKey(
        "finance.LedgerEntry",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="subscription_payment_entries",
    )
    payment_reference = models.CharField(max_length=160, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subscription_invoices"
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal_amount__gte=0)
                & Q(tax_amount__gte=0)
                & Q(total_amount=models.F("subtotal_amount") + models.F("tax_amount")),
                name="ck_subscription_invoice_totals",
            )
        ]
        indexes = [
            models.Index(fields=["office", "status", "due_at"], name="ix_subscription_invoice_due"),
        ]


class SubscriptionChangeRequest(UUIDPrimaryKeyModel):
    class EffectiveMode(models.TextChoices):
        IMMEDIATE = "immediate", "Immediate"
        NEXT_PERIOD = "next_period", "Next period"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        APPLIED = "applied", "Applied"
        CANCELLED = "cancelled", "Cancelled"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="subscription_changes")
    current_subscription = models.ForeignKey(
        OfficeSubscription,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="change_requests",
    )
    requested_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.RESTRICT, related_name="change_requests")
    effective_mode = models.CharField(max_length=20, choices=EffectiveMode.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="subscription_change_requests"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="reviewed_subscription_changes",
    )
    reason = models.TextField(null=True, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "subscription_change_requests"
        constraints = [
            models.UniqueConstraint(
                fields=["office"],
                condition=Q(status="pending"),
                name="uq_pending_subscription_change",
            )
        ]
        indexes = [models.Index(fields=["office", "status", "requested_at"], name="ix_subscription_change_queue")]
