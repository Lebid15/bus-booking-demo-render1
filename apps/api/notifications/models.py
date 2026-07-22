from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import UUIDPrimaryKeyModel


class NotificationTemplate(UUIDPrimaryKeyModel):
    class Channel(models.TextChoices):
        IN_APP = "in_app", "In app"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        PUSH = "push", "Push"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    code = models.CharField(max_length=80)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    language = models.CharField(max_length=5, default="ar")
    version = models.PositiveIntegerField(default=1)
    subject_template = models.CharField(max_length=240, blank=True)
    body_template = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PUBLISHED)
    effective_from = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_templates"
        constraints = [
            models.UniqueConstraint(
                fields=["code", "channel", "language", "version"],
                name="uq_notification_template_version",
            )
        ]
        indexes = [
            models.Index(
                fields=["code", "channel", "language", "status", "-effective_from"],
                name="ix_notif_tpl_lookup",
            )
        ]
        ordering = ["code", "channel", "language", "-version"]


class Notification(UUIDPrimaryKeyModel):
    class RecipientType(models.TextChoices):
        USER = "user", "User"
        OFFICE = "office", "Office"
        BOOKING_CONTACT = "booking_contact", "Booking contact"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PARTIALLY_SENT = "partially_sent", "Partially sent"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    source_event_id = models.UUIDField()
    dedupe_key = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=80)
    recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)
    recipient_id = models.UUIDField(null=True, blank=True)
    booking = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="notifications",
    )
    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.RESTRICT,
        related_name="notifications",
    )
    language = models.CharField(max_length=5, default="ar")
    payload = models.JSONField(default=dict)
    rendered_subject = models.CharField(max_length=240, blank=True)
    rendered_body = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    action_required = models.BooleanField(default=False)
    action_url = models.CharField(max_length=500, null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        indexes = [
            models.Index(fields=["recipient_type", "recipient_id", "-created_at"], name="ix_notif_recipient"),
            models.Index(fields=["status", "-created_at"], name="ix_notif_status"),
            models.Index(fields=["booking", "-created_at"], name="ix_notif_booking"),
        ]
        ordering = ["-created_at", "id"]


class NotificationDelivery(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        BOUNCED = "bounced", "Bounced"
        CANCELLED = "cancelled", "Cancelled"

    notification = models.ForeignKey(Notification, on_delete=models.RESTRICT, related_name="deliveries")
    channel = models.CharField(max_length=20, choices=NotificationTemplate.Channel.choices)
    destination_hash = models.BinaryField(null=True, blank=True)
    destination_ciphertext = models.BinaryField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=160, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    attempt_no = models.PositiveSmallIntegerField(default=1)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, null=True, blank=True)
    permanent_failure = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "channel", "attempt_no"],
                name="uq_notification_delivery_attempt",
            )
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="ix_notif_delivery_due"),
            models.Index(fields=["notification", "channel", "-attempt_no"], name="ix_notif_delivery_hist"),
        ]
        ordering = ["notification", "channel", "attempt_no"]


class NotificationPreference(UUIDPrimaryKeyModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="notification_preferences"
    )
    event_type = models.CharField(max_length=80)
    channel = models.CharField(max_length=20, choices=NotificationTemplate.Channel.choices)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_preferences"
        constraints = [
            models.UniqueConstraint(fields=["user", "event_type", "channel"], name="uq_notification_preference")
        ]


class PushSubscription(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"
        INVALID = "invalid", "Invalid"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="push_subscriptions")
    device = models.ForeignKey(
        "identity.UserDevice",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="push_subscriptions",
    )
    platform = models.CharField(max_length=20)
    token_hash = models.BinaryField(unique=True)
    token_ciphertext = models.BinaryField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "push_subscriptions"
        indexes = [models.Index(fields=["user", "status"], name="ix_push_user_state")]


class NotificationEscalation(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    notification = models.OneToOneField(Notification, on_delete=models.RESTRICT, related_name="escalation")
    support_case = models.ForeignKey(
        "support.SupportCase",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="notification_escalations",
    )
    reason_code = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification_escalations"
        constraints = [
            models.CheckConstraint(
                condition=Q(status="open", resolved_at__isnull=True) | Q(status="resolved", resolved_at__isnull=False),
                name="ck_notification_escalation_resolution",
            )
        ]
