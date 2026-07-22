from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class SupportCase(UUIDPrimaryKeyModel):
    class Priority(models.TextChoices):
        P0 = "P0", "P0"
        P1 = "P1", "P1"
        P2 = "P2", "P2"
        P3 = "P3", "P3"
        P4 = "P4", "P4"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ASSIGNED = "assigned", "Assigned"
        AWAITING_CUSTOMER = "awaiting_customer", "Awaiting customer"
        AWAITING_OFFICE = "awaiting_office", "Awaiting office"
        ESCALATED = "escalated", "Escalated"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.RESTRICT, related_name="support_cases"
    )
    trip = models.ForeignKey(
        "trips.Trip", null=True, blank=True, on_delete=models.RESTRICT, related_name="support_cases"
    )
    office = models.ForeignKey(
        "organizations.Office", null=True, blank=True, on_delete=models.RESTRICT, related_name="support_cases"
    )
    opened_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="opened_support_cases",
    )
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.P3)
    category = models.CharField(max_length=60)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="owned_support_cases",
    )
    sla_due_at = models.DateTimeField(null=True, blank=True)
    resolution_code = models.CharField(max_length=80, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "support_cases"
        constraints = [
            models.CheckConstraint(
                condition=Q(priority__in=["P0", "P1", "P2", "P3", "P4"]),
                name="ck_support_priority",
            )
        ]
        indexes = [
            models.Index(fields=["office", "status", "priority"], name="ix_support_office_queue"),
            models.Index(fields=["status", "sla_due_at"], name="ix_support_sla_due"),
        ]
        ordering = ["priority", "sla_due_at", "opened_at"]


class SupportMessage(UUIDPrimaryKeyModel):
    class SenderType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OFFICE = "office", "Office"
        PLATFORM = "platform", "Platform"
        SYSTEM = "system", "System"

    class Visibility(models.TextChoices):
        SHARED = "shared", "Shared"
        INTERNAL = "internal", "Internal"

    case = models.ForeignKey(SupportCase, on_delete=models.RESTRICT, related_name="messages")
    sender_type = models.CharField(max_length=20, choices=SenderType.choices)
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="support_messages",
    )
    body = models.TextField()
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.SHARED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "support_messages"
        indexes = [models.Index(fields=["case", "created_at"], name="ix_support_message_case")]
        ordering = ["created_at", "id"]


class OfficeViolation(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        CLOSED = "closed", "Closed"

    office = models.ForeignKey("organizations.Office", on_delete=models.RESTRICT, related_name="violations")
    support_case = models.ForeignKey(SupportCase, on_delete=models.RESTRICT, related_name="violations")
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=8, default="P1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "office_violations"
        constraints = [models.UniqueConstraint(fields=["support_case", "code"], name="uq_support_case_violation_code")]
        indexes = [models.Index(fields=["office", "status"], name="ix_violation_office_status")]
