from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.db.models import Case, Count, DecimalField, Sum, Value, When
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adminops.models import PlatformActionApproval
from adminops.serializers import (
    OfficeStatusActionSerializer,
    OfficeStatusCommandSerializer,
    OfficeViolationCommandSerializer,
    OfficeViolationSerializer,
    OfficeViolationWriteSerializer,
    PlatformApprovalCommandSerializer,
    PlatformApprovalSerializer,
)
from adminops.services import (
    command_platform_approval,
    request_office_status_change,
)
from auditlog.models import AuditLog
from auditlog.services import record_audit
from bookings.models import Booking
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.requests import require_idempotency_key
from finance.models import LedgerPosting
from identity.models import User
from organizations.models import Office
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from support.models import OfficeViolation, SupportCase
from trips.models import Trip


def _ledger_summary(*, office: Office | None, day: Any) -> list[dict[str, object]]:
    queryset = LedgerPosting.objects.filter(entry__occurred_at__date=day)
    if office is not None:
        queryset = queryset.filter(entry__office=office)
    rows = (
        queryset.values("entry__currency")
        .annotate(
            debit=Sum(
                Case(
                    When(direction="D", then="amount"),
                    default=Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            ),
            credit=Sum(
                Case(
                    When(direction="C", then="amount"),
                    default=Value(0),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            ),
            postings=Count("id"),
        )
        .order_by("entry__currency")
    )
    result: list[dict[str, object]] = []
    for row in rows:
        debit = row["debit"] or Decimal("0")
        credit = row["credit"] or Decimal("0")
        result.append(
            {
                "currency": str(row["entry__currency"]),
                "debit": str(debit),
                "credit": str(credit),
                "balanced": debit == credit,
                "postings": int(row["postings"]),
                "source": "ledger_postings",
            }
        )
    return result


def _office(office_id: str, *, for_update: bool = False) -> Office:
    queryset = Office.objects.select_for_update() if for_update else Office.objects.all()
    try:
        return queryset.get(public_id=office_id)
    except Office.DoesNotExist as exc:
        raise DomainAPIException("RESOURCE_NOT_FOUND") from exc


def _violation(office: Office, violation_id: str, *, for_update: bool = False) -> OfficeViolation:
    queryset = OfficeViolation.objects.select_for_update() if for_update else OfficeViolation.objects.all()
    try:
        return queryset.select_related("support_case").get(id=violation_id, office=office)
    except (OfficeViolation.DoesNotExist, ValueError) as exc:
        raise DomainAPIException("RESOURCE_NOT_FOUND") from exc


class PlatformOfficeDetailView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.office.manage"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, office_id: str) -> Response:
        office = _office(office_id)
        return Response(
            {
                "id": office.public_id,
                "legal_name": office.legal_name,
                "trade_name": office.trade_name,
                "status": office.status,
                "timezone": office.timezone,
                "default_currency": office.default_currency,
                "branches_count": office.branches.count(),
                "members_count": office.memberships.count(),
                "open_violations": office.violations.filter(status=OfficeViolation.Status.OPEN).count(),
                "status_history": OfficeStatusActionSerializer(office.status_actions.all()[:20], many=True).data,
            }
        )


class PlatformOfficeStatusView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.office.manage"

    @extend_schema(request=OfficeStatusCommandSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request, office_id: str) -> Response:
        office = _office(office_id)
        serializer = OfficeStatusCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = cast(dict[str, Any], serializer.validated_data)
        response = request_office_status_change(
            office=office,
            new_status=str(payload["status"]),
            reason=str(payload["reason"]),
            actor=cast(User, request.user),
            request=request,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(response)


class PlatformApprovalListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.approval.manage"

    @extend_schema(
        parameters=[OpenApiParameter("status", str, required=False)],
        responses={200: PlatformApprovalSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        rows = PlatformActionApproval.objects.select_related("requested_by", "approved_by").order_by("-requested_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            rows = rows.filter(status=status_filter)
        return Response(PlatformApprovalSerializer(rows[:100], many=True).data)


class PlatformApprovalCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.approval.manage"

    @extend_schema(request=PlatformApprovalCommandSerializer, responses={200: PlatformApprovalSerializer})
    def post(self, request: Request, approval_id: str) -> Response:
        approval = PlatformActionApproval.objects.filter(public_id=approval_id).first()
        if approval is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = PlatformApprovalCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = cast(dict[str, Any], serializer.validated_data)
        updated = command_platform_approval(
            approval=approval,
            command=str(payload["command"]),
            reason=str(payload["reason"]),
            actor=cast(User, request.user),
            request=request,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(PlatformApprovalSerializer(updated).data)


class PlatformOfficeViolationListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.violation.manage"

    @extend_schema(responses={200: OfficeViolationSerializer(many=True)})
    def get(self, request: Request, office_id: str) -> Response:
        office = _office(office_id)
        rows = office.violations.select_related("support_case").all()
        return Response(OfficeViolationSerializer(rows, many=True).data)

    @extend_schema(request=OfficeViolationWriteSerializer, responses={200: OfficeViolationSerializer})
    @transaction.atomic
    def post(self, request: Request, office_id: str) -> Response:
        office = _office(office_id, for_update=True)
        serializer = OfficeViolationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = cast(dict[str, Any], serializer.validated_data)
        key = require_idempotency_key(request)
        idem, replay = begin_idempotency(
            scope_type="platform_office_violation",
            scope_id=office.id,
            key=key,
            payload=payload,
        )
        if replay is not None:
            return Response(replay)

        severity = str(payload["severity"])
        support_case = SupportCase.objects.create(
            office=office,
            opened_by_user=cast(User, request.user),
            priority=severity,
            category="platform_violation",
            status=SupportCase.Status.OPEN,
            sla_due_at=timezone.now(),
            metadata={"source": "platform_admin", "code": str(payload["code"])},
        )
        violation = OfficeViolation.objects.create(
            office=office,
            support_case=support_case,
            code=str(payload["code"]),
            severity=severity,
            details={
                "description": str(payload["description"]),
                "evidence": payload.get("evidence", {}),
            },
        )
        record_audit(
            action="platform.office.violation.created",
            object_type="office_violation",
            object_id=violation.id,
            actor_user=cast(User, request.user),
            office_id=office.id,
            request=request,
            after=cast(dict[str, Any], OfficeViolationSerializer(violation).data),
        )
        response = cast(dict[str, Any], OfficeViolationSerializer(violation).data)
        complete_idempotency(idem, response)
        return Response(response)


class PlatformOfficeViolationCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.violation.manage"

    @extend_schema(request=OfficeViolationCommandSerializer, responses={200: OfficeViolationSerializer})
    @transaction.atomic
    def post(self, request: Request, office_id: str, violation_id: str) -> Response:
        office = _office(office_id, for_update=True)
        violation = _violation(office, violation_id, for_update=True)
        serializer = OfficeViolationCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = cast(dict[str, Any], serializer.validated_data)
        key = require_idempotency_key(request)
        idem, replay = begin_idempotency(
            scope_type="platform_office_violation_command",
            scope_id=violation.id,
            key=key,
            payload=payload,
        )
        if replay is not None:
            return Response(replay)

        previous = violation.status
        command = str(payload["command"])
        if command == "acknowledge":
            violation.status = OfficeViolation.Status.ACKNOWLEDGED
            violation.save(update_fields=["status"])
        elif command == "close":
            violation.status = OfficeViolation.Status.CLOSED
            violation.closed_at = timezone.now()
            violation.save(update_fields=["status", "closed_at"])
            violation.support_case.status = SupportCase.Status.CLOSED
            violation.support_case.closed_at = timezone.now()
            violation.support_case.resolution_code = "platform_violation_closed"
            violation.support_case.save(update_fields=["status", "closed_at", "resolution_code"])
        record_audit(
            action=f"platform.office.violation.{command}",
            object_type="office_violation",
            object_id=violation.id,
            actor_user=cast(User, request.user),
            office_id=office.id,
            request=request,
            before={"status": previous},
            after={"status": violation.status},
            reason_code=str(payload["reason"]),
        )
        response = cast(dict[str, Any], OfficeViolationSerializer(violation).data)
        complete_idempotency(idem, response)
        return Response(response)


class PlatformAuditView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.audit.view"

    @extend_schema(
        parameters=[
            OpenApiParameter("office_id", str, required=False),
            OpenApiParameter("action", str, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        queryset = AuditLog.objects.select_related("actor_user")
        if office_id := request.query_params.get("office_id"):
            office = _office(office_id)
            queryset = queryset.filter(office_id=office.id)
        if action := request.query_params.get("action"):
            queryset = queryset.filter(action__icontains=action)
        rows = queryset[:200]
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "occurred_at": row.occurred_at,
                        "actor": row.actor_user.email if row.actor_user else None,
                        "action": row.action,
                        "object_type": row.object_type,
                        "object_id": row.object_id,
                        "reason_code": row.reason_code,
                        "metadata": row.metadata,
                    }
                    for row in rows
                ]
            }
        )


class PlatformReportsSummaryView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.report.view"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        today = timezone.localdate()
        bookings = Booking.objects.filter(created_at__date=today)
        return Response(
            {
                "date": today,
                "offices": {
                    "total": Office.objects.count(),
                    "active": Office.objects.filter(status=Office.Status.ACTIVE).count(),
                    "suspended": Office.objects.filter(status=Office.Status.SUSPENDED).count(),
                },
                "trips": {"today": Trip.objects.filter(scheduled_departure_at__date=today).count()},
                "bookings": {
                    "today": bookings.count(),
                    "by_status": list(bookings.values("status").annotate(count=Count("id"))),
                },
                "finance": {
                    "source": "ledger_postings",
                    "by_currency": _ledger_summary(office=None, day=today),
                },
                "violations": {"open": OfficeViolation.objects.filter(status=OfficeViolation.Status.OPEN).count()},
            }
        )


class OfficeReportsSummaryView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.report.view"

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        office = request.office_context.office
        today = timezone.localdate()
        bookings = Booking.objects.filter(office=office, created_at__date=today)
        return Response(
            {
                "date": today,
                "trips_today": Trip.objects.filter(
                    office=office,
                    scheduled_departure_at__date=today,
                ).count(),
                "bookings_today": bookings.count(),
                "booking_statuses": list(bookings.values("status").annotate(count=Count("id"))),
                "finance": {
                    "source": "ledger_postings",
                    "by_currency": _ledger_summary(office=office, day=today),
                },
                "open_violations": office.violations.filter(status=OfficeViolation.Status.OPEN).count(),
            }
        )
