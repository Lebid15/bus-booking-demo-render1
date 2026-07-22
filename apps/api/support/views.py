from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from support.models import SupportCase, SupportMessage
from support.serializers import (
    GuestSupportCaseRequestSerializer,
    SupportCaseCommandSerializer,
    SupportCaseSerializer,
    SupportMessageRequestSerializer,
    SupportMessageSerializer,
)
from support.services import (
    add_support_message,
    command_support_case,
    open_guest_support_case,
    recovery_lookup,
)


def _office_case(request: Any, case_id: str) -> SupportCase:
    case = (
        SupportCase.objects.select_related("booking", "trip", "office")
        .filter(public_id=case_id, office=request.office_context.office)
        .first()
    )
    if case is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return case


def _platform_case(case_id: str) -> SupportCase:
    case = SupportCase.objects.select_related("booking", "trip", "office").filter(public_id=case_id).first()
    if case is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return case


class PublicBookingSupportCaseView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=GuestSupportCaseRequestSerializer, responses={200: SupportCaseSerializer})
    def post(self, request, pnr: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = GuestSupportCaseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = open_guest_support_case(
            pnr=pnr,
            manage_token=request.query_params.get("manage_token", ""),
            data=serializer.validated_data,
            request=request,
            idempotency_key=key,
        )
        return Response(SupportCaseSerializer(case).data)


class OfficeSupportCaseListView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.support.manage"

    @extend_schema(
        responses={200: SupportCaseSerializer(many=True)},
        parameters=[OpenApiParameter("priority", str, required=False), OpenApiParameter("status", str, required=False)],
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = SupportCase.objects.filter(office=request.office_context.office).select_related(
            "booking", "trip", "office"
        )
        if request.query_params.get("priority"):
            queryset = queryset.filter(priority=request.query_params["priority"])
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        return Response(SupportCaseSerializer(queryset, many=True).data)


class OfficeSupportMessageView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.support.manage"

    @extend_schema(responses={200: SupportMessageSerializer(many=True)})
    def get(self, request, case_id: str):  # type: ignore[no-untyped-def]
        case = _office_case(request, case_id)
        return Response(SupportMessageSerializer(case.messages.filter(visibility="shared"), many=True).data)

    @extend_schema(request=SupportMessageRequestSerializer, responses={200: SupportMessageSerializer})
    def post(self, request, case_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        case = _office_case(request, case_id)
        serializer = SupportMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = add_support_message(
            case=case,
            actor=request.user,
            sender_type=SupportMessage.SenderType.OFFICE,
            body=str(serializer.validated_data["body"]),
            visibility=str(serializer.validated_data["visibility"]),
            request=request,
            idempotency_key=key,
        )
        return Response(SupportMessageSerializer(message).data)


class PlatformSupportCaseListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.support.manage"

    @extend_schema(
        responses={200: SupportCaseSerializer(many=True)},
        parameters=[
            OpenApiParameter("priority", str, required=False),
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("office_id", str, required=False),
        ],
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = SupportCase.objects.select_related("booking", "trip", "office")
        if request.query_params.get("priority"):
            queryset = queryset.filter(priority=request.query_params["priority"])
        if request.query_params.get("status"):
            queryset = queryset.filter(status=request.query_params["status"])
        if request.query_params.get("office_id"):
            queryset = queryset.filter(office__public_id=request.query_params["office_id"])
        return Response(SupportCaseSerializer(queryset, many=True).data)


class PlatformSupportMessageView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.support.manage"

    @extend_schema(responses={200: SupportMessageSerializer(many=True)})
    def get(self, request, case_id: str):  # type: ignore[no-untyped-def]
        case = _platform_case(case_id)
        return Response(SupportMessageSerializer(case.messages.all(), many=True).data)

    @extend_schema(request=SupportMessageRequestSerializer, responses={200: SupportMessageSerializer})
    def post(self, request, case_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        case = _platform_case(case_id)
        serializer = SupportMessageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = add_support_message(
            case=case,
            actor=request.user,
            sender_type=SupportMessage.SenderType.PLATFORM,
            body=str(serializer.validated_data["body"]),
            visibility=str(serializer.validated_data["visibility"]),
            request=request,
            idempotency_key=key,
        )
        return Response(SupportMessageSerializer(message).data)


class PlatformSupportCaseCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.support.manage"

    @extend_schema(request=SupportCaseCommandSerializer, responses={200: SupportCaseSerializer})
    def post(self, request, case_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        case = _platform_case(case_id)
        serializer = SupportCaseCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = command_support_case(
            case=case,
            actor=request.user,
            command=str(serializer.validated_data["command"]),
            resolution_code=str(serializer.validated_data.get("resolution_code") or "") or None,
            request=request,
            idempotency_key=key,
        )
        return Response(SupportCaseSerializer(updated).data)


class OfficeRecoveryLookupView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.boarding.scan"

    @extend_schema(
        responses={200: dict},
        parameters=[
            OpenApiParameter("pnr", str, required=True),
            OpenApiParameter("identity_tail", str, required=False),
        ],
    )
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        return Response(
            recovery_lookup(
                context=request.office_context,
                trip_id=trip_id,
                pnr=request.query_params.get("pnr", ""),
                identity_tail=request.query_params.get("identity_tail"),
            )
        )
