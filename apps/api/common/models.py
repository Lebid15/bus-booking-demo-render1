from __future__ import annotations

import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class IdempotencyKey(UUIDPrimaryKeyModel):
    scope_type = models.CharField(max_length=80)
    scope_id = models.UUIDField(null=True, blank=True)
    key = models.CharField(max_length=120)
    request_hash = models.CharField(max_length=64)
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_keys"
        constraints = [
            models.UniqueConstraint(fields=["scope_type", "scope_id", "key"], name="uq_idempotency_scope_key")
        ]


class OutboxEvent(UUIDPrimaryKeyModel):
    aggregate_type = models.CharField(max_length=80)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=120)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "outbox_events"
        indexes = [models.Index(fields=["published_at", "next_attempt_at"], name="ix_outbox_pending")]
