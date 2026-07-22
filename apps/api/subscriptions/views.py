from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from identity.models import User
from organizations.models import Office
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from subscriptions.models import (
    SubscriptionChangeRequest,
    SubscriptionInvoice,
    SubscriptionPlan,
)
from subscriptions.serializers import (
    InvoicePaymentSerializer,
    OfficeSubscriptionSerializer,
    SetOfficeSubscriptionSerializer,
    SubscriptionChangeRequestSerializer,
    SubscriptionChangeRequestWriteSerializer,
    SubscriptionPlanPatchSerializer,
    SubscriptionPlanSerializer,
)
from subscriptions.services import (
    assign_subscription,
    close_invoice,
    create_plan,
    current_subscription,
    mark_invoice_paid,
    request_change,
    review_change_request,
    serialize_invoice,
    serialize_plan,
    serialize_subscription,
    update_plan,
)


def _plan(plan_id: str) -> SubscriptionPlan:
    plan = SubscriptionPlan.objects.filter(public_id=plan_id).first()
    if plan is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return plan


def _office(office_id: str) -> Office:
    office = Office.objects.filter(public_id=office_id).first()
    if office is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return office


class OfficeSubscriptionView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.subscription.view"

    @extend_schema(responses={200: OfficeSubscriptionSerializer})
    def get(self, request: Request) -> Response:
        subscription = current_subscription(request.office_context.office)
        if subscription is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        return Response(serialize_subscription(subscription))


class OfficeAvailablePlansView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.subscription.view"

    @extend_schema(responses={200: SubscriptionPlanSerializer(many=True)})
    def get(self, request: Request) -> Response:
        now = timezone.now()
        queryset = SubscriptionPlan.objects.filter(
            status=SubscriptionPlan.Status.ACTIVE,
            effective_from__lte=now,
        ).order_by("price_amount", "code")
        rows = [row for row in queryset if row.effective_to is None or row.effective_to > now]
        return Response([serialize_plan(row) for row in rows])


class OfficeSubscriptionChangeRequestView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.subscription.change"

    @extend_schema(
        request=SubscriptionChangeRequestWriteSerializer,
        responses={200: SubscriptionChangeRequestSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = SubscriptionChangeRequestWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        change = request_change(
            context=request.office_context,
            actor=cast(User, request.user),
            request=request,
            plan=_plan(str(data["plan_id"])),
            effective_mode=str(data["effective_mode"]),
            idempotency_key=require_idempotency_key(request),
        )
        return Response(
            {
                "request_id": change.public_id,
                "status": change.status,
                "plan_id": change.requested_plan.public_id,
                "effective_mode": change.effective_mode,
                "requested_at": change.requested_at,
            }
        )


class PlatformSubscriptionPlanListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.manage"

    @extend_schema(responses={200: SubscriptionPlanSerializer(many=True)})
    def get(self, request: Request) -> Response:
        rows = SubscriptionPlan.objects.order_by("code", "-version")
        return Response([serialize_plan(row) for row in rows])

    @extend_schema(request=SubscriptionPlanSerializer, responses={200: SubscriptionPlanSerializer})
    def post(self, request: Request) -> Response:
        serializer = SubscriptionPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = create_plan(
            actor=cast(User, request.user),
            request=request,
            data=cast(dict[str, Any], serializer.validated_data),
            idempotency_key=require_idempotency_key(request),
        )
        return Response(serialize_plan(plan))


class PlatformSubscriptionPlanDetailView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.manage"

    @extend_schema(request=SubscriptionPlanPatchSerializer, responses={200: SubscriptionPlanSerializer})
    def patch(self, request: Request, plan_id: str) -> Response:
        serializer = SubscriptionPlanPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = update_plan(
            plan=_plan(plan_id),
            actor=cast(User, request.user),
            request=request,
            data=cast(dict[str, Any], serializer.validated_data),
            idempotency_key=require_idempotency_key(request),
        )
        return Response(serialize_plan(plan))


class PlatformOfficeSubscriptionView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.manage"

    @extend_schema(request=SetOfficeSubscriptionSerializer, responses={200: OfficeSubscriptionSerializer})
    def post(self, request: Request, office_id: str) -> Response:
        serializer = SetOfficeSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        subscription = assign_subscription(
            office=_office(office_id),
            plan=_plan(str(data["plan_id"])),
            actor=cast(User, request.user),
            request=request,
            idempotency_key=require_idempotency_key(request),
            requested_status=str(data.get("status", "active")),
            period_start=data.get("period_start"),
            period_end=data.get("period_end"),
            auto_renew=bool(data.get("auto_renew", False)),
            payment_reference=str(data["payment_reference"]) if data.get("payment_reference") else None,
        )
        return Response(serialize_subscription(subscription))


class PlatformSubscriptionInvoiceListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.billing"

    @extend_schema(
        parameters=[
            OpenApiParameter("office_id", str, required=False),
            OpenApiParameter("status", str, required=False),
        ],
        responses={200: dict},
    )
    def get(self, request: Request) -> Response:
        rows = SubscriptionInvoice.objects.select_related("office", "office_subscription").order_by("-created_at")
        office_id = request.query_params.get("office_id")
        status_value = request.query_params.get("status")
        if office_id:
            rows = rows.filter(office__public_id=office_id)
        if status_value:
            rows = rows.filter(status=status_value)
        return Response([serialize_invoice(row) for row in rows[:200]])


class PlatformSubscriptionInvoiceCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.billing"

    @extend_schema(request=InvoicePaymentSerializer, responses={200: dict})
    def post(self, request: Request, invoice_id: str) -> Response:
        invoice = SubscriptionInvoice.objects.filter(public_id=invoice_id).first()
        if invoice is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = InvoicePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = cast(dict[str, Any], serializer.validated_data)
        command = str(data["command"])
        key = require_idempotency_key(request)
        actor = cast(User, request.user)
        if command == "mark_paid":
            reference = str(data.get("payment_reference") or "").strip()
            if not reference:
                raise DomainAPIException("VALIDATION_ERROR", details={"field": "payment_reference"})
            updated = mark_invoice_paid(
                invoice=invoice,
                payment_reference=reference,
                actor=actor,
                request=request,
                idempotency_key=key,
            )
        else:
            updated = close_invoice(
                invoice=invoice,
                command=command,
                actor=actor,
                request=request,
                idempotency_key=key,
                reason=str(data.get("reason") or ""),
            )
        return Response(serialize_invoice(updated))


class PlatformSubscriptionChangeListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.manage"

    @extend_schema(responses={200: dict})
    def get(self, request: Request) -> Response:
        rows = SubscriptionChangeRequest.objects.select_related("office", "requested_plan").order_by("-requested_at")
        return Response(
            [
                {
                    "request_id": row.public_id,
                    "office_id": row.office.public_id,
                    "office_name": row.office.trade_name,
                    "plan_id": row.requested_plan.public_id,
                    "plan_name": row.requested_plan.name_ar,
                    "effective_mode": row.effective_mode,
                    "status": row.status,
                    "requested_at": row.requested_at,
                }
                for row in rows[:200]
            ]
        )


class PlatformSubscriptionChangeCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.subscription.manage"

    @extend_schema(request=dict, responses={200: dict})
    @transaction.atomic
    def post(self, request: Request, request_id: str) -> Response:
        change = SubscriptionChangeRequest.objects.filter(public_id=request_id).first()
        if change is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        command = str(request.data.get("command", ""))
        if command not in {"approve", "reject"}:
            raise DomainAPIException("VALIDATION_ERROR")
        updated = review_change_request(
            change=change,
            command=command,
            actor=cast(User, request.user),
            request=request,
            idempotency_key=require_idempotency_key(request),
            payment_reference=str(request.data.get("payment_reference") or "") or None,
            reason=str(request.data.get("reason") or ""),
        )
        record_audit(
            action="platform.subscription.change.reviewed",
            object_type="subscription_change_request",
            object_id=updated.id,
            actor_user=cast(User, request.user),
            office_id=updated.office_id,
            request=request,
            after={"status": updated.status},
        )
        return Response({"request_id": updated.public_id, "status": updated.status})
