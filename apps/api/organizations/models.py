from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from common.ids import generate_public_id
from identity.models import Role


class TransportOperator(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=160, null=True, blank=True)
    registration_number = models.CharField(max_length=100, null=True, blank=True)
    status = models.CharField(max_length=24, default="draft")
    country_code = models.CharField(max_length=2, default="SY")
    support_phone = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "transport_operators"


class Office(models.Model):
    class OfficeType(models.TextChoices):
        CARRIER = "carrier", "Carrier"
        BRANCH = "branch", "Branch"
        AUTHORIZED_AGENT = "authorized_agent", "Authorized agent"
        GARAGE_OFFICE = "garage_office", "Garage office"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        CONDITIONAL = "conditional", "Conditional"
        ACTIVE = "active", "Active"
        RESTRICTED = "restricted", "Restricted"
        NO_NEW_BOOKINGS = "no_new_bookings", "No new bookings"
        WIND_DOWN = "wind_down", "Wind down"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    operator = models.ForeignKey(
        TransportOperator,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="offices",
    )
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=160)
    office_type = models.CharField(max_length=24, choices=OfficeType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    timezone = models.CharField(max_length=64, default="Asia/Damascus")
    default_currency = models.CharField(max_length=3, default="SYP")
    support_phone = models.CharField(max_length=20)
    support_email = models.EmailField(null=True, blank=True)
    commission_profile_id = models.UUIDField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "offices"


class OfficeBranch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="branches")
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    name = models.CharField(max_length=160)
    location = models.ForeignKey("geography.Location", on_delete=models.RESTRICT, related_name="office_branches")
    phone = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=20, default="active")
    is_primary = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "office_branches"
        constraints = [
            models.UniqueConstraint(fields=["office", "name"], name="uq_office_branch_name"),
            models.UniqueConstraint(
                fields=["office"], condition=Q(is_primary=True), name="uq_primary_branch"
            ),
        ]


class OfficeMembershipQuerySet(models.QuerySet["OfficeMembership"]):
    def active(self) -> OfficeMembershipQuerySet:
        return self.filter(status=OfficeMembership.Status.ACTIVE, revoked_at__isnull=True)

    def for_user(self, user: Any) -> OfficeMembershipQuerySet:
        return self.active().filter(user=user)


class OfficeMembership(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INVITED = "invited", "Invited"
        SUSPENDED = "suspended", "Suspended"
        REVOKED = "revoked", "Revoked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="office_memberships")
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="memberships")
    branch = models.ForeignKey(
        OfficeBranch,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="memberships",
    )
    role = models.ForeignKey(Role, on_delete=models.RESTRICT, related_name="memberships")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    can_approve_own_actions = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = OfficeMembershipQuerySet.as_manager()

    class Meta:
        db_table = "office_memberships"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "office", "branch", "role"],
                name="uq_membership_nullsafe",
                nulls_distinct=False,
            )
        ]


class VerificationCase(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        INFO_REQUIRED = "info_required", "Information required"
        EXTERNAL_VERIFICATION = "external_verification", "External verification"
        CONDITIONAL = "conditional", "Conditional"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    class RiskLevel(models.TextChoices):
        BASIC = "basic", "Basic"
        DOCUMENTED = "documented", "Documented"
        ENHANCED = "enhanced", "Enhanced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="verification_cases")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    risk_level = models.CharField(max_length=12, choices=RiskLevel.choices, default=RiskLevel.BASIC)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reviewer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="verification_reviews",
    )
    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="verification_approvals",
    )
    decision_reason = models.TextField(null=True, blank=True)
    conditions = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "verification_cases"
        constraints = [
            models.UniqueConstraint(fields=["office", "version"], name="uq_verification_case_version")
        ]
        indexes = [
            models.Index(fields=["status", "risk_level"], name="ix_verification_status_risk"),
            models.Index(fields=["office", "-version"], name="ix_verification_office_version"),
        ]
        ordering = ["-version"]


class OfficeDocument(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="documents")
    verification_case = models.ForeignKey(
        VerificationCase,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="documents",
    )
    document_type = models.CharField(max_length=64)
    storage_object_key = models.TextField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    issued_at = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    is_critical = models.BooleanField(default=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="reviewed_office_documents",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "office_documents"
        constraints = [
            models.UniqueConstraint(
                fields=["office", "document_type", "sha256"],
                name="uq_office_document_hash",
            )
        ]
        indexes = [
            models.Index(fields=["office", "status", "expires_at"], name="ix_office_doc_validity")
        ]


class OfficePayoutAccount(models.Model):
    class MethodType(models.TextChoices):
        BANK = "bank", "Bank"
        WALLET = "wallet", "Wallet"
        CASH_CLEARING = "cash_clearing", "Cash clearing"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REPLACED = "replaced", "Replaced"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="payout_accounts")
    method_type = models.CharField(max_length=30, choices=MethodType.choices)
    account_holder_name = models.CharField(max_length=200)
    account_reference_ciphertext = models.BinaryField()
    account_reference_last4 = models.CharField(max_length=8, null=True, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    verified_at = models.DateTimeField(null=True, blank=True)
    effective_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_payout_accounts",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_payout_accounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "office_payout_accounts"
        constraints = [
            models.CheckConstraint(
                condition=Q(approved_by__isnull=True) | ~Q(approved_by=F("created_by")),
                name="ck_payout_dual_approval",
            ),
            models.UniqueConstraint(
                fields=["office"],
                condition=Q(status="active"),
                name="uq_active_payout_account",
            ),
        ]
