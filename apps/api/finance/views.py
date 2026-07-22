from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from finance.dispute_services import (
    command_dispute,
    file_dispute_appeal,
    list_office_disputes,
    list_platform_disputes,
    office_respond_dispute,
    serialize_dispute,
)
from finance.models import CommissionProfile, FinancialDispute, Settlement
from finance.serializers import (
    CommissionProfilePatchSerializer,
    CommissionProfileSerializer,
    CreateSettlementSerializer,
    DisputeAppealSerializer,
    DisputeCommandSerializer,
    OfficeDisputeResponseSerializer,
    SettlementCommandSerializer,
    SettlementSerializer,
)
from finance.services import (
    command_settlement,
    create_commission_profile,
    create_settlement,
    list_office_settlements,
    list_platform_settlements,
    serialize_commission_profile,
    serialize_settlement,
    update_commission_profile,
)
from organizations.permissions import HasOfficeContext, HasPlatformAccess


class OfficeSettlementListView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.finance.view"

    @extend_schema(responses={200: SettlementSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(list_office_settlements(request.office_context))


class PlatformSettlementListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.settlement.manage"

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("office_id", str, required=False),
        ],
        responses={200: SettlementSerializer(many=True)},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(
            list_platform_settlements(
                status=request.query_params.get("status"),
                office_id=request.query_params.get("office_id"),
            )
        )

    @extend_schema(request=CreateSettlementSerializer, responses={200: SettlementSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = CreateSettlementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        settlement = create_settlement(
            actor=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            **serializer.validated_data,
        )
        return Response(SettlementSerializer(serialize_settlement(settlement)).data)


class PlatformSettlementCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.settlement.approve"

    @extend_schema(request=SettlementCommandSerializer, responses={200: SettlementSerializer})
    def post(self, request, settlement_id: str):  # type: ignore[no-untyped-def]
        settlement = Settlement.objects.filter(public_id=settlement_id).first()
        if settlement is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = SettlementCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = command_settlement(
            settlement=settlement,
            actor=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            **serializer.validated_data,
        )
        return Response(SettlementSerializer(serialize_settlement(updated)).data)


class PlatformCommissionProfileListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.commission.manage"

    @extend_schema(responses={200: CommissionProfileSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        rows = [serialize_commission_profile(item) for item in CommissionProfile.objects.order_by("code", "-version")]
        return Response(rows)

    @extend_schema(request=CommissionProfileSerializer, responses={200: CommissionProfileSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = CommissionProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = create_commission_profile(
            actor=request.user,
            request=request,
            data=serializer.validated_data,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(CommissionProfileSerializer(serialize_commission_profile(profile)).data)


class PlatformCommissionProfileDetailView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.commission.manage"

    @extend_schema(request=CommissionProfilePatchSerializer, responses={200: CommissionProfileSerializer})
    def patch(self, request, profile_id: str):  # type: ignore[no-untyped-def]
        profile = CommissionProfile.objects.filter(public_id=profile_id).first()
        if profile is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = CommissionProfilePatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = update_commission_profile(
            profile=profile,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(CommissionProfileSerializer(serialize_commission_profile(updated)).data)


class PlatformDisputeListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.dispute.manage"

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("office_id", str, required=False),
        ],
        responses={200: dict},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(
            list_platform_disputes(
                status_filter=request.query_params.get("status"), office_id=request.query_params.get("office_id")
            )
        )


class PlatformDisputeCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.dispute.manage"

    @extend_schema(request=DisputeCommandSerializer, responses={200: dict})
    def post(self, request, dispute_id: str):  # type: ignore[no-untyped-def]
        dispute = FinancialDispute.objects.filter(id=dispute_id).first()
        if dispute is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = DisputeCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        command = str(data.pop("command"))
        updated = command_dispute(
            dispute=dispute,
            command=command,
            data=data,
            actor=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            platform_permissions=getattr(request, "platform_permissions", frozenset()),
        )
        return Response(serialize_dispute(updated))


class OfficeDisputeListView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.support.manage"

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        return Response(list_office_disputes(context=request.office_context))


class OfficeDisputeResponseView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.support.manage"

    @extend_schema(request=OfficeDisputeResponseSerializer, responses={200: dict})
    def post(self, request, dispute_id: str):  # type: ignore[no-untyped-def]
        dispute = FinancialDispute.objects.filter(id=dispute_id).first()
        if dispute is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = OfficeDisputeResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = office_respond_dispute(
            dispute=dispute,
            context=request.office_context,
            actor=request.user,
            data=dict(serializer.validated_data),
            request=request,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(serialize_dispute(updated))


class OfficeDisputeAppealView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.support.manage"

    @extend_schema(request=DisputeAppealSerializer, responses={200: dict})
    def post(self, request, dispute_id: str):  # type: ignore[no-untyped-def]
        dispute = FinancialDispute.objects.select_related("booking").filter(id=dispute_id).first()
        if dispute is None or dispute.booking.office_id != request.office_context.office.id:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = DisputeAppealSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = file_dispute_appeal(
            dispute=dispute,
            filed_by_type="office",
            actor=request.user,
            reason=str(serializer.validated_data["reason"]),
            evidence=dict(serializer.validated_data.get("evidence", {})),
            request=request,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(serialize_dispute(updated))
