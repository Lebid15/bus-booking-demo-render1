from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from common.exceptions import DomainAPIException
from continuity.models import BackupRun, Incident, PlatformContinuityState, ReleaseRun
from continuity.services import (
    change_mode,
    create_incident,
    current_state,
    incident_command,
    record_load_test,
    record_recovery_exercise,
    record_release,
    run_reconciliation,
)
from identity.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _actor() -> User:
    return User.objects.create_user(
        full_name="Continuity Commander",
        email=f"continuity-{uuid.uuid4().hex[:8]}@example.com",
        is_platform_staff=True,
    )


def _request(actor: User):  # type: ignore[no-untyped-def]
    request = RequestFactory().post("/v1/platform/continuity/commands", REMOTE_ADDR="203.0.113.7")
    request.user = actor
    return request


def test_e18_ac01_recovery_mode_blocks_writes_but_not_reads(api_client: APIClient) -> None:
    PlatformContinuityState.objects.create(mode=PlatformContinuityState.Mode.RECOVERY, reconciliation_required=True)
    read_response = api_client.get("/health/live")
    write_response = api_client.post("/v1/public/bookings/lookup", {}, format="json")

    assert read_response.status_code == 200
    assert write_response.status_code == 503
    assert write_response.json()["error"]["code"] == "PLATFORM_MAINTENANCE"


def test_e18_ac02_recovery_exercise_enforces_rpo_and_rto() -> None:
    actor = _actor()
    now = timezone.now()
    backup = BackupRun.objects.create(
        status=BackupRun.Status.SUCCEEDED,
        started_at=now - timedelta(minutes=20),
        completed_at=now - timedelta(minutes=15),
        source_wal_at=now - timedelta(minutes=5),
    )
    passed = record_recovery_exercise(
        data={
            "backup_id": backup.public_id,
            "target_time": now,
            "restored_to_time": now - timedelta(minutes=5),
            "started_at": now - timedelta(minutes=30),
            "completed_at": now,
            "evidence": {"restore_verified": True},
        },
        actor=actor,
        request=_request(actor),
    )
    failed = record_recovery_exercise(
        data={
            "backup_id": backup.public_id,
            "target_time": now,
            "restored_to_time": now - timedelta(minutes=16),
            "started_at": now - timedelta(hours=5),
            "completed_at": now,
            "evidence": {},
        },
        actor=actor,
        request=_request(actor),
    )

    assert passed.status == "passed"
    assert passed.rpo_seconds == 300
    assert passed.rto_seconds == 1800
    assert failed.status == "failed"


def test_e18_ac03_reopen_requires_successful_reconciliation() -> None:
    actor = _actor()
    request = _request(actor)
    change_mode(command="recovery", actor=actor, request=request, reason="database failover")

    with pytest.raises(DomainAPIException) as blocked:
        change_mode(command="reopen", actor=actor, request=request, reason="too early")
    assert blocked.value.code == "RECOVERY_RECONCILIATION_REQUIRED"

    run = run_reconciliation(actor=actor, request=request)
    state = change_mode(command="reopen", actor=actor, request=request, reason="reconciled")

    assert run.status == "passed"
    assert state.mode == "normal"
    assert state.reconciliation_required is False


def test_e18_ac04_failed_smoke_requires_and_records_rollback() -> None:
    with pytest.raises(DomainAPIException) as missing:
        record_release(data={"version": "v-test", "health_passed": True, "smoke_passed": False, "evidence": {}})
    assert missing.value.code == "RELEASE_ROLLBACK_REQUIRED"
    assert ReleaseRun.objects.count() == 0

    run = record_release(
        data={
            "version": "v-test",
            "health_passed": True,
            "smoke_passed": False,
            "rollback_reference": "v-previous",
            "evidence": {"smoke": "failed"},
        }
    )
    assert run.status == "rolled_back"
    assert run.rollback_required is True


def test_e18_ac05_sev1_requires_commander_timeline_communications_and_postmortem() -> None:
    actor = _actor()
    incident = create_incident(
        data={
            "title": "Database unavailable",
            "severity": "SEV1",
            "communication_channel": "#sev1-db",
            "customer_impact": "Bookings paused",
        },
        actor=actor,
    )
    incident_command(incident=incident, command="timeline", message="Failover started", postmortem="", actor=actor)
    incident_command(incident=incident, command="resolve", message="", postmortem="", actor=actor)

    with pytest.raises(DomainAPIException) as missing:
        incident_command(incident=incident, command="close", message="", postmortem="", actor=actor)
    assert missing.value.code == "INCIDENT_POSTMORTEM_REQUIRED"

    incident = incident_command(
        incident=incident,
        command="close",
        message="",
        postmortem="Root cause and actions documented",
        actor=actor,
    )
    assert incident.status == Incident.Status.CLOSED
    assert incident.timeline.count() == 2


def test_e18_ac06_load_gate_rejects_duplicate_seats_or_financial_entries() -> None:
    now = timezone.now()
    passed = record_load_test(
        {
            "scenario": "launch peak",
            "started_at": now - timedelta(minutes=10),
            "completed_at": now,
            "requests": 5000,
            "error_rate_percent": "0.200",
            "p95_ms": 800,
            "duplicate_seats": 0,
            "duplicate_financial_entries": 0,
            "slo": {"max_error_rate_percent": 1, "max_p95_ms": 1500},
        }
    )
    failed = record_load_test(
        {
            "scenario": "unsafe peak",
            "started_at": now - timedelta(minutes=10),
            "completed_at": now,
            "requests": 5000,
            "error_rate_percent": "0.100",
            "p95_ms": 700,
            "duplicate_seats": 1,
            "duplicate_financial_entries": 0,
            "slo": {"max_error_rate_percent": 1, "max_p95_ms": 1500},
        }
    )
    assert passed.status == "passed"
    assert failed.status == "failed"


def test_ready_health_includes_continuity_state(api_client: APIClient) -> None:
    current_state()
    response = api_client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["continuity"] == "ok"
