from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from common.ids import generate_public_id


class OfficeStatusAction(models.Model):
    """Append-only history for platform office lifecycle decisions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="status_actions")
    previous_status = models.CharField(max_length=24)
    new_status = models.CharField(max_length=24)
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="office_status_actions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "office_status_actions"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["office", "-created_at"], name="ix_office_status_history")]

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.pk and OfficeStatusAction.objects.filter(pk=self.pk).exists():
            raise RuntimeError("Office status actions are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("Office status actions are append-only")


class PlatformActionApproval(models.Model):
    """Dual-control envelope for critical platform mutations."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXECUTED = "executed", "Executed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    action_type = models.CharField(max_length=80)
    target_type = models.CharField(max_length=60)
    target_id = models.UUIDField()
    payload = models.JSONField(default=dict)
    risk_level = models.CharField(max_length=12, default="critical")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField()
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="requested_platform_approvals",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="approved_platform_approvals",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_action_approvals"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(approved_by__isnull=True) | ~models.Q(approved_by=models.F("requested_by")),
                name="ck_platform_approval_dual_control",
            )
        ]
        indexes = [
            models.Index(fields=["status", "action_type", "requested_at"], name="ix_platform_approval_queue"),
            models.Index(fields=["target_type", "target_id"], name="ix_platform_approval_target"),
        ]
