from __future__ import annotations

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="audit_events",
    )
    actor_type = models.CharField(max_length=20)
    office_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=80)
    object_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    ip_hash = models.BinaryField(null=True, blank=True)
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    reason_code = models.CharField(max_length=80, null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "audit_logs"
        indexes = [models.Index(fields=["occurred_at"], name="ix_audit_time")]
        ordering = ["-occurred_at"]

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise RuntimeError("Audit logs are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("Audit logs are append-only")
