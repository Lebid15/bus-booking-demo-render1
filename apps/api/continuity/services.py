from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import SeatAssignment
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from continuity.models import (
    BackupRun,
    Incident,
    IncidentTimelineEntry,
    LoadTestRun,
    PlatformContinuityState,
    ReconciliationRun,
    RecoveryExercise,
    ReleaseRun,
)
from finance.models import LedgerEntry, LedgerPosting
from identity.models import User
from payments.models import PaymentTransaction


def current_state(*, lock: bool = False) -> PlatformContinuityState:
    queryset = PlatformContinuityState.objects.all()
    if lock:
        queryset = queryset.select_for_update()
    state = queryset.filter(singleton_key="platform").first()
    if state is None:
        state = PlatformContinuityState.objects.create(singleton_key="platform")
    return state


def serialize_state(state: PlatformContinuityState) -> dict[str, Any]:
    return {
        "mode": state.mode,
        "reason": state.reason,
        "reconciliation_required": state.reconciliation_required,
        "last_reconciled_at": state.last_reconciled_at.isoformat() if state.last_reconciled_at else None,
        "changed_at": state.changed_at.isoformat() if state.changed_at else None,
    }


def _seat_conflicts() -> int:
    # Database constraints should keep this at zero; this check makes recovery reopening explicit.
    duplicates = (
        SeatAssignment.objects.filter(status=SeatAssignment.Status.ACTIVE)
        .values("trip_id", "trip_seat_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    return duplicates.count()


def _payment_conflicts() -> int:
    duplicates = (
        PaymentTransaction.objects.exclude(provider_event_id__isnull=True)
        .exclude(provider_event_id="")
        .values("provider_event_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    return duplicates.count()


def _ledger_conflicts() -> int:
    conflicts = 0
    for entry in LedgerEntry.objects.all().iterator():
        debit = sum(
            (
                posting.amount
                for posting in LedgerPosting.objects.filter(entry=entry, direction=LedgerPosting.Direction.DEBIT)
            ),
            start=0,
        )
        credit = sum(
            (
                posting.amount
                for posting in LedgerPosting.objects.filter(entry=entry, direction=LedgerPosting.Direction.CREDIT)
            ),
            start=0,
        )
        if debit != credit:
            conflicts += 1
    return conflicts


@transaction.atomic
def change_mode(*, command: str, actor: User, request: HttpRequest, reason: str) -> PlatformContinuityState:
    state = current_state(lock=True)
    before = serialize_state(state)
    if command == "maintenance":
        state.mode = PlatformContinuityState.Mode.MAINTENANCE
    elif command == "recovery":
        state.mode = PlatformContinuityState.Mode.RECOVERY
        state.reconciliation_required = True
    elif command == "reopen":
        if state.reconciliation_required:
            raise DomainAPIException("RECOVERY_RECONCILIATION_REQUIRED")
        latest = ReconciliationRun.objects.order_by("-started_at").first()
        if latest is None or latest.status != ReconciliationRun.Status.PASSED:
            raise DomainAPIException("RECOVERY_RECONCILIATION_REQUIRED")
        state.mode = PlatformContinuityState.Mode.NORMAL
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    state.reason = reason
    state.changed_by = actor
    state.save()
    record_audit(
        action="continuity.mode_changed",
        object_type="platform_continuity_state",
        actor_user=actor,
        object_id=state.id,
        request=request,
        before=before,
        after=serialize_state(state),
        reason_code=reason or command,
    )
    OutboxEvent.objects.create(
        aggregate_type="platform_continuity_state",
        aggregate_id=state.id,
        event_type="continuity.mode.changed",
        payload={"mode": state.mode, "reason": reason},
    )
    return state


@transaction.atomic
def run_reconciliation(*, actor: User, request: HttpRequest) -> ReconciliationRun:
    state = current_state(lock=True)
    if state.mode not in {PlatformContinuityState.Mode.RECOVERY, PlatformContinuityState.Mode.RECONCILIATION}:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    state.mode = PlatformContinuityState.Mode.RECONCILIATION
    state.save(update_fields=["mode", "changed_at"])
    run = ReconciliationRun.objects.create(started_at=timezone.now(), triggered_by=actor)
    run.seat_conflicts = _seat_conflicts()
    run.payment_conflicts = _payment_conflicts()
    run.ledger_conflicts = _ledger_conflicts()
    run.completed_at = timezone.now()
    run.status = (
        ReconciliationRun.Status.PASSED
        if run.seat_conflicts + run.payment_conflicts + run.ledger_conflicts == 0
        else ReconciliationRun.Status.FAILED
    )
    run.evidence_json = {
        "seat_conflicts": run.seat_conflicts,
        "payment_conflicts": run.payment_conflicts,
        "ledger_conflicts": run.ledger_conflicts,
    }
    run.save()
    if run.status == ReconciliationRun.Status.PASSED:
        state.reconciliation_required = False
        state.last_reconciled_at = run.completed_at
    state.save(update_fields=["reconciliation_required", "last_reconciled_at", "changed_at"])
    record_audit(
        action="continuity.reconciliation_completed",
        object_type="reconciliation_run",
        actor_user=actor,
        object_id=run.id,
        request=request,
        after={"status": run.status, **run.evidence_json},
    )
    return run


@transaction.atomic
def record_recovery_exercise(*, data: dict[str, Any], actor: User, request: HttpRequest) -> RecoveryExercise:
    backup = BackupRun.objects.filter(public_id=str(data["backup_id"]), status=BackupRun.Status.SUCCEEDED).first()
    if backup is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    started_at = data["started_at"]
    completed_at = data["completed_at"]
    target_time = data["target_time"]
    restored_to_time = data["restored_to_time"]
    rpo_seconds = int(abs((target_time - restored_to_time).total_seconds()))
    rto_seconds = int((completed_at - started_at).total_seconds())
    passed = rpo_seconds <= 900 and rto_seconds <= 14400
    exercise = RecoveryExercise.objects.create(
        backup=backup,
        status=RecoveryExercise.Status.PASSED if passed else RecoveryExercise.Status.FAILED,
        started_at=started_at,
        completed_at=completed_at,
        target_time=target_time,
        restored_to_time=restored_to_time,
        rpo_seconds=rpo_seconds,
        rto_seconds=rto_seconds,
        evidence_json=data.get("evidence") or {},
        failure_reason="" if passed else "RPO/RTO objective missed",
    )
    record_audit(
        action="continuity.recovery_exercise_recorded",
        object_type="recovery_exercise",
        actor_user=actor,
        object_id=exercise.id,
        request=request,
        after={"status": exercise.status, "rpo_seconds": rpo_seconds, "rto_seconds": rto_seconds},
    )
    return exercise


def record_release(*, data: dict[str, Any]) -> ReleaseRun:
    passed = bool(data["health_passed"]) and bool(data["smoke_passed"])
    rollback_reference = str(data.get("rollback_reference") or "")
    if not passed and not rollback_reference:
        raise DomainAPIException("RELEASE_ROLLBACK_REQUIRED")
    run = ReleaseRun.objects.create(
        version=str(data["version"]),
        status=ReleaseRun.Status.PASSED if passed else ReleaseRun.Status.ROLLED_BACK,
        health_passed=bool(data["health_passed"]),
        smoke_passed=bool(data["smoke_passed"]),
        rollback_required=not passed,
        rollback_reference=rollback_reference,
        started_at=timezone.now(),
        completed_at=timezone.now(),
        evidence_json=data.get("evidence") or {},
    )
    return run


def create_incident(*, data: dict[str, Any], actor: User) -> Incident:
    if data["severity"] == Incident.Severity.SEV1 and not data.get("communication_channel"):
        raise DomainAPIException("INCIDENT_COMMANDER_REQUIRED")
    incident = Incident.objects.create(
        title=str(data["title"]),
        severity=str(data["severity"]),
        commander=actor,
        opened_at=timezone.now(),
        communication_channel=str(data["communication_channel"]),
        customer_impact=str(data.get("customer_impact") or ""),
    )
    IncidentTimelineEntry.objects.create(
        incident=incident, occurred_at=timezone.now(), event_type="opened", message="Incident opened", actor=actor
    )
    return incident


def incident_command(*, incident: Incident, command: str, message: str, postmortem: str, actor: User) -> Incident:
    if command == "timeline":
        if not message:
            raise DomainAPIException("VALIDATION_ERROR")
        IncidentTimelineEntry.objects.create(
            incident=incident, occurred_at=timezone.now(), event_type="update", message=message, actor=actor
        )
    elif command == "mitigate":
        incident.status = Incident.Status.MITIGATED
    elif command == "resolve":
        incident.status = Incident.Status.RESOLVED
        incident.resolved_at = timezone.now()
    elif command == "close":
        if incident.severity == Incident.Severity.SEV1 and not postmortem.strip():
            raise DomainAPIException("INCIDENT_POSTMORTEM_REQUIRED")
        incident.status = Incident.Status.CLOSED
        incident.postmortem = postmortem
    incident.save()
    return incident


def record_load_test(data: dict[str, Any]) -> LoadTestRun:
    slo = data.get("slo") or {}
    max_error = float(slo.get("max_error_rate_percent", 1.0))
    max_p95 = int(slo.get("max_p95_ms", 1500))
    passed = (
        float(data["error_rate_percent"]) <= max_error
        and int(data["p95_ms"]) <= max_p95
        and int(data["duplicate_seats"]) == 0
        and int(data["duplicate_financial_entries"]) == 0
    )
    return LoadTestRun.objects.create(
        scenario=str(data["scenario"]),
        status=LoadTestRun.Status.PASSED if passed else LoadTestRun.Status.FAILED,
        started_at=data["started_at"],
        completed_at=data["completed_at"],
        requests=int(data["requests"]),
        error_rate_percent=data["error_rate_percent"],
        p95_ms=int(data["p95_ms"]),
        duplicate_seats=int(data["duplicate_seats"]),
        duplicate_financial_entries=int(data["duplicate_financial_entries"]),
        slo_json=slo,
    )
