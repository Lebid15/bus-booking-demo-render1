from __future__ import annotations

from django.conf import settings
from django.db import models

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class PlatformContinuityState(UUIDPrimaryKeyModel):
    class Mode(models.TextChoices):
        NORMAL = "normal", "Normal"
        MAINTENANCE = "maintenance", "Maintenance"
        RECOVERY = "recovery", "Recovery"
        RECONCILIATION = "reconciliation", "Reconciliation"

    singleton_key = models.CharField(max_length=20, unique=True, default="platform")
    mode = models.CharField(max_length=24, choices=Mode.choices, default=Mode.NORMAL)
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.RESTRICT, related_name="continuity_changes"
    )
    changed_at = models.DateTimeField(auto_now=True)
    reconciliation_required = models.BooleanField(default=False)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_continuity_state"


class BackupRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED)
    backup_type = models.CharField(max_length=30, default="full")
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    source_wal_at = models.DateTimeField(null=True, blank=True)
    artifact_uri = models.CharField(max_length=500, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "backup_runs"
        indexes = [models.Index(fields=["status", "started_at"], name="ix_backup_run_status")]


class RecoveryExercise(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    backup = models.ForeignKey(BackupRun, on_delete=models.RESTRICT, related_name="recovery_exercises")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    target_time = models.DateTimeField()
    restored_to_time = models.DateTimeField(null=True, blank=True)
    rpo_seconds = models.PositiveIntegerField(null=True, blank=True)
    rto_seconds = models.PositiveIntegerField(null=True, blank=True)
    evidence_json = models.JSONField(default=dict)
    failure_reason = models.TextField(blank=True)

    class Meta:
        db_table = "recovery_exercises"


class ReconciliationRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    seat_conflicts = models.PositiveIntegerField(default=0)
    payment_conflicts = models.PositiveIntegerField(default=0)
    ledger_conflicts = models.PositiveIntegerField(default=0)
    evidence_json = models.JSONField(default=dict)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.RESTRICT, related_name="reconciliation_runs"
    )

    class Meta:
        db_table = "reconciliation_runs"
        indexes = [models.Index(fields=["status", "started_at"], name="ix_reconciliation_status")]


class ReleaseRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"
        ROLLED_BACK = "rolled_back", "Rolled back"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    version = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    health_passed = models.BooleanField(default=False)
    smoke_passed = models.BooleanField(default=False)
    rollback_required = models.BooleanField(default=False)
    rollback_reference = models.CharField(max_length=200, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    evidence_json = models.JSONField(default=dict)

    class Meta:
        db_table = "release_runs"
        indexes = [models.Index(fields=["status", "started_at"], name="ix_release_status")]


class Incident(UUIDPrimaryKeyModel):
    class Severity(models.TextChoices):
        SEV1 = "SEV1", "SEV-1"
        SEV2 = "SEV2", "SEV-2"
        SEV3 = "SEV3", "SEV-3"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        MITIGATED = "mitigated", "Mitigated"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    title = models.CharField(max_length=240)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    commander = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="commanded_incidents"
    )
    opened_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    communication_channel = models.CharField(max_length=240)
    customer_impact = models.TextField(blank=True)
    postmortem = models.TextField(blank=True)

    class Meta:
        db_table = "incidents"


class IncidentTimelineEntry(UUIDPrimaryKeyModel):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="timeline")
    occurred_at = models.DateTimeField()
    event_type = models.CharField(max_length=80)
    message = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.RESTRICT)

    class Meta:
        db_table = "incident_timeline_entries"
        ordering = ["occurred_at", "id"]


class LoadTestRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PASSED = "passed", "Passed"
        FAILED = "failed", "Failed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    scenario = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=Status.choices)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField()
    requests = models.PositiveIntegerField(default=0)
    error_rate_percent = models.DecimalField(max_digits=6, decimal_places=3, default=0)
    p95_ms = models.PositiveIntegerField(default=0)
    duplicate_seats = models.PositiveIntegerField(default=0)
    duplicate_financial_entries = models.PositiveIntegerField(default=0)
    slo_json = models.JSONField(default=dict)

    class Meta:
        db_table = "load_test_runs"
