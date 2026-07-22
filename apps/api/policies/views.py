from __future__ import annotations

from typing import cast

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.requests import require_idempotency_key
from organizations.models import Office
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from organizations.services import OfficeContext
from policies.models import ConfigurationValue, PolicyVersion
from policies.serializers import (
    ConfigurationChangeSerializer,
    ConfigurationPatchSerializer,
    PolicyVersionSerializer,
    PolicyVersionWriteSerializer,
)
from policies.services import (
    approve_configuration_changes,
    create_policy_version,
    effective_configuration,
    get_public_policy,
    propose_configuration_changes,
)


class PlatformPolicyListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.policy.manage"

    @extend_schema(responses={200: PolicyVersionSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = PolicyVersion.objects.select_related("template", "office").all()
        return Response(PolicyVersionSerializer(queryset, many=True).data)

    @extend_schema(request=PolicyVersionWriteSerializer, responses={200: PolicyVersionSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = PolicyVersionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy, _ = create_policy_version(
            actor=request.user,
            request=request,
            data=serializer.validated_data,
            idempotency_key=key,
        )
        return Response(PolicyVersionSerializer(policy).data)


class PublicPolicyDetailView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[
            OpenApiParameter(name="office_id", type=str, required=False),
            OpenApiParameter(name="language", type=str, required=False),
        ],
        responses={200: PolicyVersionSerializer},
    )
    def get(self, request, policy_code: str):  # type: ignore[no-untyped-def]
        office = None
        office_id = request.query_params.get("office_id")
        if office_id:
            office = Office.objects.filter(public_id=office_id).first()
        policy = get_public_policy(code=policy_code, office=office)
        language = request.query_params.get("language")
        if language and policy.language != language:
            candidate = PolicyVersion.objects.filter(
                template=policy.template,
                office=policy.office,
                language=language,
                published_at__isnull=False,
                effective_from__lte=timezone.now(),
            ).order_by("-version_no").first()
            if candidate is not None:
                policy = candidate
        return Response(PolicyVersionSerializer(policy).data)


class OfficeConfigurationView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.configuration.manage"

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = cast(OfficeContext, request.office_context)
        pending = ConfigurationValue.objects.filter(
            scope_type=ConfigurationValue.ScopeType.OFFICE,
            scope_id=context.office.id,
            approved_by__isnull=True,
        )
        return Response(
            {
                "effective": effective_configuration(
                    scope_type=ConfigurationValue.ScopeType.OFFICE,
                    scope_id=context.office.id,
                ),
                "pending_changes": ConfigurationChangeSerializer(pending, many=True).data,
            }
        )

    @extend_schema(request=ConfigurationPatchSerializer, responses={200: dict})
    def patch(self, request):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = ConfigurationPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        context = cast(OfficeContext, request.office_context)
        rows = propose_configuration_changes(
            scope_type=ConfigurationValue.ScopeType.OFFICE,
            scope_id=context.office.id,
            actor=request.user,
            request=request,
            changes=dict(serializer.validated_data["changes"]),
            reason=str(serializer.validated_data["reason"]),
            effective_from=serializer.validated_data.get("effective_from") or timezone.now(),
            idempotency_key=key,
            auto_approve=True,
        )
        return Response(
            {
                "effective": effective_configuration(
                    scope_type=ConfigurationValue.ScopeType.OFFICE,
                    scope_id=context.office.id,
                ),
                "changes": ConfigurationChangeSerializer(rows, many=True).data,
            }
        )


class PlatformConfigurationView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.configuration.manage"

    @extend_schema(responses={200: dict})
    def get(self, request):  # type: ignore[no-untyped-def]
        pending = ConfigurationValue.objects.filter(
            scope_type=ConfigurationValue.ScopeType.PLATFORM,
            scope_id__isnull=True,
            approved_by__isnull=True,
        )
        return Response(
            {
                "effective": effective_configuration(scope_type=ConfigurationValue.ScopeType.PLATFORM),
                "pending_changes": ConfigurationChangeSerializer(pending, many=True).data,
            }
        )

    @extend_schema(request=ConfigurationPatchSerializer, responses={200: dict})
    def patch(self, request):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = ConfigurationPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = str(serializer.validated_data.get("action", "propose"))
        if action == "approve":
            rows = approve_configuration_changes(
                actor=request.user,
                request=request,
                change_ids=list(serializer.validated_data["change_ids"]),
                reason=str(serializer.validated_data["reason"]),
                idempotency_key=key,
            )
        else:
            rows = propose_configuration_changes(
                scope_type=ConfigurationValue.ScopeType.PLATFORM,
                scope_id=None,
                actor=request.user,
                request=request,
                changes=dict(serializer.validated_data["changes"]),
                reason=str(serializer.validated_data["reason"]),
                effective_from=serializer.validated_data.get("effective_from") or timezone.now(),
                idempotency_key=key,
                auto_approve=False,
            )
        return Response(
            {
                "effective": effective_configuration(scope_type=ConfigurationValue.ScopeType.PLATFORM),
                "changes": ConfigurationChangeSerializer(rows, many=True).data,
            }
        )
