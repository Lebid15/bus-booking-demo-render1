from __future__ import annotations

from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from continuity.models import BackupRun, Incident, LoadTestRun, ReconciliationRun, RecoveryExercise, ReleaseRun
from continuity.serializers import (
    ContinuityCommandSerializer,
    IncidentCommandSerializer,
    IncidentSerializer,
    LoadTestSerializer,
    RecoveryExerciseSerializer,
    ReleaseSerializer,
)
from continuity.services import (
    change_mode,
    create_incident,
    current_state,
    incident_command,
    record_load_test,
    record_recovery_exercise,
    record_release,
    run_reconciliation,
    serialize_state,
)
from identity.models import User
from organizations.permissions import HasPlatformAccess


def _reconciliation(row: ReconciliationRun) -> dict[str, Any]:
    return {
        "run_id": row.public_id,
        "status": row.status,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "seat_conflicts": row.seat_conflicts,
        "payment_conflicts": row.payment_conflicts,
        "ledger_conflicts": row.ledger_conflicts,
    }


class ContinuityOverviewView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.continuity.manage"

    @extend_schema(responses={200: dict})
    def get(self, request: Request) -> Response:
        state = current_state()
        latest_reconciliation = ReconciliationRun.objects.order_by("-started_at").first()
        return Response(
            {
                "state": serialize_state(state),
                "latest_reconciliation": _reconciliation(latest_reconciliation) if latest_reconciliation else None,
                "latest_backup": BackupRun.objects.order_by("-started_at")
                .values("public_id", "status", "started_at", "completed_at")
                .first(),
                "latest_recovery": RecoveryExercise.objects.order_by("-started_at")
                .values("public_id", "status", "rpo_seconds", "rto_seconds")
                .first(),
                "latest_release": ReleaseRun.objects.order_by("-started_at")
                .values("public_id", "version", "status")
                .first(),
                "open_sev1": Incident.objects.filter(severity="SEV1", status__in=["open", "mitigated"]).count(),
                "latest_load_test": LoadTestRun.objects.order_by("-started_at")
                .values("public_id", "scenario", "status", "p95_ms")
                .first(),
            }
        )


class ContinuityCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.continuity.manage"

    @extend_schema(request=ContinuityCommandSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = ContinuityCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        if data["command"] == "reconcile":
            return Response(_reconciliation(run_reconciliation(actor=cast(User, request.user), request=request)))
        return Response(
            serialize_state(
                change_mode(
                    command=str(data["command"]),
                    actor=cast(User, request.user),
                    request=request,
                    reason=str(data.get("reason") or ""),
                )
            )
        )


class RecoveryExerciseView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.continuity.manage"

    @extend_schema(request=RecoveryExerciseSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = RecoveryExerciseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = record_recovery_exercise(
            data=cast(dict[str, Any], serializer.validated_data), actor=cast(User, request.user), request=request
        )
        return Response(
            {
                "exercise_id": row.public_id,
                "status": row.status,
                "rpo_seconds": row.rpo_seconds,
                "rto_seconds": row.rto_seconds,
            }
        )


class ReleaseRunView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.release.manage"

    @extend_schema(request=ReleaseSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = ReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = record_release(data=cast(dict[str, Any], serializer.validated_data))
        return Response({"release_id": row.public_id, "status": row.status, "rollback_required": row.rollback_required})


class IncidentListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.incident.manage"

    @extend_schema(responses={200: list[dict[str, Any]]})
    def get(self, request: Request) -> Response:
        return Response(
            [
                {
                    "incident_id": r.public_id,
                    "title": r.title,
                    "severity": r.severity,
                    "status": r.status,
                    "commander": r.commander.full_name,
                }
                for r in Incident.objects.select_related("commander").order_by("-opened_at")[:100]
            ]
        )

    @extend_schema(request=IncidentSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = IncidentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = create_incident(data=cast(dict[str, Any], serializer.validated_data), actor=cast(User, request.user))
        return Response({"incident_id": row.public_id, "status": row.status})


class IncidentCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.incident.manage"

    @extend_schema(request=IncidentCommandSerializer, responses={200: dict})
    def post(self, request: Request, incident_id: str) -> Response:
        incident = Incident.objects.filter(public_id=incident_id).first()
        if incident is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = IncidentCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        row = incident_command(
            incident=incident,
            command=str(data["command"]),
            message=str(data.get("message") or ""),
            postmortem=str(data.get("postmortem") or ""),
            actor=cast(User, request.user),
        )
        return Response({"incident_id": row.public_id, "status": row.status})


class LoadTestView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.release.manage"

    @extend_schema(request=LoadTestSerializer, responses={200: dict})
    def post(self, request: Request) -> Response:
        serializer = LoadTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = record_load_test(cast(dict[str, Any], serializer.validated_data))
        return Response(
            {
                "load_test_id": row.public_id,
                "status": row.status,
                "duplicate_seats": row.duplicate_seats,
                "duplicate_financial_entries": row.duplicate_financial_entries,
            }
        )
