from __future__ import annotations

from django.db import models
from django.db.models import Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class LedgerAccount(UUIDPrimaryKeyModel):
    class AccountType(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        REVENUE = "revenue", "Revenue"
        EXPENSE = "expense", "Expense"
        CONTRA = "contra", "Contra"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    office = models.ForeignKey(
        "organizations.Office",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="ledger_accounts",
    )
    code = models.CharField(max_length=80)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ledger_accounts"
        constraints = [
            models.UniqueConstraint(
                fields=["office", "code", "currency"],
                condition=Q(office__isnull=False),
                name="uq_office_ledger_account",
            ),
            models.UniqueConstraint(
                fields=["code", "currency"],
                condition=Q(office__isnull=True),
                name="uq_global_ledger_account",
            ),
        ]


class LedgerEntry(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    event_type = models.CharField(max_length=80)
    event_id = models.UUIDField()
    booking = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="ledger_entries",
    )
    trip = models.ForeignKey(
        "trips.Trip",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="ledger_entries",
    )
    office = models.ForeignKey(
        "organizations.Office",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="ledger_entries",
    )
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.POSTED)
    occurred_at = models.DateTimeField()
    posted_at = models.DateTimeField(auto_now_add=True)
    reversal_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="reversals",
    )
    description = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "ledger_entries"
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "event_id", "currency"],
                name="uq_ledger_event_currency",
            ),
            models.CheckConstraint(
                condition=Q(reversal_of__isnull=True) | Q(status="reversed"),
                name="ck_ledger_reversal_status",
            ),
        ]


class LedgerPosting(UUIDPrimaryKeyModel):
    class Direction(models.TextChoices):
        DEBIT = "D", "Debit"
        CREDIT = "C", "Credit"

    entry = models.ForeignKey(LedgerEntry, on_delete=models.RESTRICT, related_name="postings")
    account = models.ForeignKey(LedgerAccount, on_delete=models.RESTRICT, related_name="postings")
    direction = models.CharField(max_length=1, choices=Direction.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    memo = models.CharField(max_length=240, null=True, blank=True)

    class Meta:
        db_table = "ledger_postings"
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_ledger_posting_positive")]


class Commission(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        EXPECTED = "expected", "Expected"
        PENDING = "pending", "Pending"
        EARNED = "earned", "Earned"
        IN_SETTLEMENT = "in_settlement", "In settlement"
        PAID = "paid", "Paid"
        REVERSED = "reversed", "Reversed"
        ADJUSTED = "adjusted", "Adjusted"

    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="commission",
    )
    office = models.ForeignKey(
        "organizations.Office",
        on_delete=models.RESTRICT,
        related_name="commissions",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.EXPECTED)
    basis_amount = models.DecimalField(max_digits=18, decimal_places=2)
    rate = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    earned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commissions"
        constraints = [
            models.CheckConstraint(
                condition=Q(basis_amount__gte=0)
                & Q(rate__gte=0)
                & Q(fixed_amount__gte=0)
                & Q(commission_amount__gte=0),
                name="ck_commission_nonnegative",
            )
        ]


class CommissionProfile(UUIDPrimaryKeyModel):
    class CalculationType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed"
        HYBRID = "hybrid", "Hybrid"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    calculation_type = models.CharField(max_length=20, choices=CalculationType.choices)
    percentage_rate = models.DecimalField(max_digits=9, decimal_places=6, default=0)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    effective_from = models.DateTimeField(null=True, blank=True)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.RESTRICT, related_name="superseded_by"
    )
    created_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="created_commission_profiles"
    )
    approved_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_commission_profiles",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "commission_profiles"
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="uq_commission_profile_version"),
            models.CheckConstraint(
                condition=Q(percentage_rate__gte=0) & Q(fixed_amount__gte=0),
                name="ck_commission_profile_nonnegative",
            ),
        ]
        indexes = [models.Index(fields=["code", "status", "-version"], name="ix_commission_profile_current")]


class FinancialDispute(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        AWAITING_OFFICE = "awaiting_office", "Awaiting office"
        UNDER_REVIEW = "under_review", "Under review"
        DECIDED = "decided", "Decided"
        APPEALED = "appealed", "Appealed"
        CLOSED = "closed", "Closed"

    class OpenedByType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OFFICE = "office", "Office"
        PLATFORM = "platform", "Platform"
        PROVIDER = "provider", "Provider"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.RESTRICT, related_name="financial_disputes")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    category = models.CharField(max_length=60)
    disputed_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)
    opened_by_type = models.CharField(max_length=20, choices=OpenedByType.choices)
    opened_by_id = models.UUIDField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="assigned_financial_disputes",
    )
    decision_code = models.CharField(max_length=80, null=True, blank=True)
    decision_summary = models.TextField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    appeal_deadline_at = models.DateTimeField(null=True, blank=True)
    appealed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "disputes"
        constraints = [
            models.CheckConstraint(
                condition=Q(disputed_amount__isnull=True) | Q(disputed_amount__gte=0),
                name="ck_dispute_amount_nonnegative",
            )
        ]
        indexes = [
            models.Index(fields=["booking", "status"], name="ix_dispute_booking_status"),
            models.Index(fields=["status", "opened_at"], name="ix_dispute_queue"),
        ]


class FinancialDisputeDecision(UUIDPrimaryKeyModel):
    class Stage(models.TextChoices):
        INITIAL = "initial", "Initial"
        APPEAL = "appeal", "Appeal"

    class FinancialEffectType(models.TextChoices):
        NONE = "none", "None"
        OFFICE_CREDIT = "office_credit", "Office credit"
        OFFICE_DEBIT = "office_debit", "Office debit"
        CUSTOMER_COMPENSATION = "customer_compensation", "Customer compensation"

    dispute = models.ForeignKey(FinancialDispute, on_delete=models.RESTRICT, related_name="decisions")
    stage = models.CharField(max_length=16, choices=Stage.choices)
    decision_code = models.CharField(max_length=80)
    reasoning = models.TextField()
    financial_effect_type = models.CharField(
        max_length=32, choices=FinancialEffectType.choices, default=FinancialEffectType.NONE
    )
    financial_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    appeal_allowed_until = models.DateTimeField(null=True, blank=True)
    is_final = models.BooleanField(default=False)
    decided_by = models.ForeignKey(
        "identity.User", on_delete=models.RESTRICT, related_name="financial_dispute_decisions"
    )
    ledger_entry = models.ForeignKey(
        LedgerEntry, null=True, blank=True, on_delete=models.RESTRICT, related_name="dispute_decisions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dispute_decisions"
        constraints = [
            models.UniqueConstraint(fields=["dispute", "stage"], name="uq_dispute_decision_stage"),
            models.CheckConstraint(condition=Q(financial_amount__gte=0), name="ck_dispute_effect_nonnegative"),
        ]
        indexes = [models.Index(fields=["dispute", "stage"], name="ix_dispute_decision_stage")]


class FinancialDisputeAppeal(UUIDPrimaryKeyModel):
    class FiledByType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OFFICE = "office", "Office"
        PLATFORM = "platform", "Platform"

    dispute = models.OneToOneField(FinancialDispute, on_delete=models.RESTRICT, related_name="appeal")
    filed_by_type = models.CharField(max_length=20, choices=FiledByType.choices)
    filed_by_user = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.RESTRICT, related_name="financial_dispute_appeals"
    )
    reason = models.TextField()
    evidence = models.JSONField(default=dict)
    filed_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "dispute_appeals"


class Settlement(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CALCULATED = "calculated", "Calculated"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CLOSED = "closed", "Closed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="settlements")
    period_start = models.DateField()
    period_end = models.DateField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    refund_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    reserve_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    adjustment_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    net_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    created_by = models.ForeignKey("identity.User", on_delete=models.RESTRICT, related_name="created_settlements")
    approved_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_settlements",
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=160, null=True, blank=True, unique=True)
    failure_reason = models.CharField(max_length=240, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "settlements"
        constraints = [
            models.UniqueConstraint(
                fields=["office", "period_start", "period_end", "currency"],
                name="uq_settlement_office_period_currency",
            ),
            models.CheckConstraint(condition=Q(period_end__gte=models.F("period_start")), name="ck_settlement_period"),
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True) | ~Q(approved_by=models.F("created_by")),
                name="ck_settlement_dual_approval",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "currency", "status"], name="ix_settlement_office_status"),
            models.Index(fields=["status", "period_end"], name="ix_settlement_platform_queue"),
        ]


class SettlementItem(UUIDPrimaryKeyModel):
    class ItemType(models.TextChoices):
        ELECTRONIC_PAYABLE = "electronic_payable", "Electronic payable"
        DIRECT_COMMISSION = "direct_commission", "Direct commission"
        NETTING = "netting", "Netting"
        REFUND = "refund", "Refund"
        RESERVE = "reserve", "Reserve"
        FROZEN_DISPUTE = "frozen_dispute", "Frozen dispute"
        ADJUSTMENT = "adjustment", "Adjustment"

    settlement = models.ForeignKey(Settlement, on_delete=models.RESTRICT, related_name="items")
    item_type = models.CharField(max_length=40, choices=ItemType.choices)
    source_type = models.CharField(max_length=40)
    source_id = models.UUIDField()
    booking = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="settlement_items",
    )
    commission = models.ForeignKey(
        Commission,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="settlement_items",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    description = models.CharField(max_length=240, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "settlement_items"
        constraints = [
            models.UniqueConstraint(
                fields=["settlement", "item_type", "source_type", "source_id"],
                name="uq_settlement_item_source",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="ck_settlement_item_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["settlement", "item_type"], name="ix_settlement_item_type"),
            models.Index(fields=["booking", "currency"], name="ix_settlement_item_booking"),
        ]
