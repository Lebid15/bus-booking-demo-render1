from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class RiskAssessment(models.Model):
    class SubjectType(models.TextChoices):
        BOOKING = "booking", "Booking"
        PAYMENT = "payment", "Payment"
        USER = "user", "User"
        OFFICE = "office", "Office"
        EMPLOYEE = "employee", "Employee"
        DEVICE = "device", "Device"

    class Decision(models.TextChoices):
        ALLOW = "allow", "Allow"
        STEP_UP = "step_up", "Step up"
        MANUAL_REVIEW = "manual_review", "Manual review"
        RESTRICT = "restrict", "Restrict"
        BLOCK = "block", "Block"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_type = models.CharField(max_length=30, choices=SubjectType.choices)
    subject_id = models.UUIDField()
    score = models.DecimalField(max_digits=6, decimal_places=3)
    decision = models.CharField(max_length=24, choices=Decision.choices)
    model_version = models.CharField(max_length=40)
    signals = models.JSONField(default=dict)
    review_status = models.CharField(max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "risk_assessments"
        constraints = [
            models.CheckConstraint(condition=Q(score__gte=0) & Q(score__lte=100), name="ck_risk_score_range")
        ]
        indexes = [
            models.Index(fields=["subject_type", "subject_id", "-created_at"], name="ix_risk_subject_time"),
            models.Index(fields=["decision", "review_status", "-created_at"], name="ix_risk_decision_review"),
        ]


class RiskChallenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.OneToOneField(RiskAssessment, on_delete=models.RESTRICT, related_name="challenge")
    code_hash = models.BinaryField()
    token_hash = models.BinaryField(null=True, blank=True, unique=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "risk_challenges"
        indexes = [models.Index(fields=["expires_at", "consumed_at"], name="ix_risk_challenge_expiry")]


class DataSubjectRequest(models.Model):
    class RequestType(models.TextChoices):
        ACCESS = "access", "Access"
        EXPORT = "export", "Export"
        CORRECT = "correct", "Correct"
        DELETE = "delete", "Delete"
        RESTRICT = "restrict", "Restrict"
        OBJECT = "object", "Object"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        IDENTITY_VERIFICATION = "identity_verification", "Identity verification"
        IN_PROGRESS = "in_progress", "In progress"
        FULFILLED = "fulfilled", "Fulfilled"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="data_subject_requests",
    )
    contact_phone = models.CharField(max_length=20, null=True, blank=True)
    request_type = models.CharField(max_length=24, choices=RequestType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "data_subject_requests"
        indexes = [models.Index(fields=["status", "due_at"], name="ix_dsr_status_due")]


class LegalHold(models.Model):
    class SubjectType(models.TextChoices):
        BOOKING = "booking", "Booking"
        USER = "user", "User"
        PAYMENT = "payment", "Payment"
        DISPUTE = "dispute", "Dispute"
        OFFICE = "office", "Office"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_type = models.CharField(max_length=40, choices=SubjectType.choices)
    subject_id = models.UUIDField()
    reason = models.TextField()
    active = models.BooleanField(default=True)
    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="placed_legal_holds",
    )
    placed_at = models.DateTimeField(auto_now_add=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="released_legal_holds",
    )
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "legal_holds"
        constraints = [
            models.UniqueConstraint(
                fields=["subject_type", "subject_id"],
                condition=Q(active=True),
                name="uq_active_legal_hold",
            )
        ]
        indexes = [models.Index(fields=["subject_type", "subject_id", "active"], name="ix_legal_hold_subject")]


class StoredFile(models.Model):
    class OwnerScope(models.TextChoices):
        USER = "user", "User"
        OFFICE = "office", "Office"
        PLATFORM = "platform", "Platform"
        BOOKING = "booking", "Booking"
        SUPPORT = "support", "Support"

    class ScanStatus(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        QUARANTINED = "quarantined", "Quarantined"
        CLEAN = "clean", "Clean"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_scope = models.CharField(max_length=30, choices=OwnerScope.choices)
    owner_id = models.UUIDField(null=True, blank=True)
    purpose = models.CharField(max_length=60)
    object_key = models.TextField(unique=True)
    original_filename = models.CharField(max_length=255, null=True, blank=True)
    mime_type = models.CharField(max_length=120)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    scan_status = models.CharField(max_length=20, choices=ScanStatus.choices, default=ScanStatus.INITIATED)
    retention_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="stored_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stored_files"
        constraints = [
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="ck_stored_file_positive_size"),
            models.UniqueConstraint(
                fields=["owner_scope", "owner_id", "purpose", "sha256"],
                name="uq_stored_file_owner_purpose_hash",
            ),
        ]
        indexes = [
            models.Index(fields=["owner_scope", "owner_id", "scan_status"], name="ix_file_owner_status"),
            models.Index(fields=["scan_status", "retention_until"], name="ix_file_retention"),
        ]
