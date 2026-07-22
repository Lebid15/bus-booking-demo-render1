from __future__ import annotations

import uuid

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from organizations.models import (
    Office,
    OfficeBranch,
    OfficeDocument,
    OfficeMembership,
    OfficePayoutAccount,
    VerificationCase,
)
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from organizations.serializers import (
    MembershipSerializer,
    OfficeBranchSerializer,
    OfficeBranchWriteSerializer,
    OfficeDocumentReviewSerializer,
    OfficeDocumentSerializer,
    OfficeDocumentWriteSerializer,
    OfficeSerializer,
    PayoutAccountSerializer,
    PayoutAccountWriteSerializer,
    StaffInviteSerializer,
    StaffUpdateSerializer,
    VerificationCaseSerializer,
    VerificationCommandSerializer,
)
from organizations.services import (
    approve_payout_account_change,
    command_verification,
    create_branch,
    invite_staff,
    latest_verification_case,
    register_office_document,
    request_payout_account_change,
    review_office_document,
    update_branch,
    update_staff,
)


class OfficeContextView(APIView):
    permission_classes = [HasOfficeContext]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request):  # type: ignore[no-untyped-def]
        context = request.office_context
        return Response(
            {
                "office": OfficeSerializer(context.office).data,
                "branch": (
                    {
                        "id": context.branch.public_id,
                        "name": context.branch.name,
                    }
                    if context.branch
                    else None
                ),
                "membership": {
                    "id": str(context.membership.id),
                    "role": context.membership.role.code,
                },
                "permissions": sorted(context.permissions),
                "configuration": {},
            }
        )


class OfficeBranchListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.branch.manage"

    @extend_schema(responses={200: OfficeBranchSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = OfficeBranch.objects.filter(office=request.office_context.office).select_related(
            "location", "location__parent"
        )
        return Response(OfficeBranchSerializer(queryset, many=True).data)

    @extend_schema(request=OfficeBranchWriteSerializer, responses={200: OfficeBranchSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = OfficeBranchWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        branch = create_branch(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        branch = OfficeBranch.objects.select_related("location", "location__parent").get(pk=branch.pk)
        return Response(OfficeBranchSerializer(branch).data)


class OfficeBranchDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.branch.manage"

    @extend_schema(request=OfficeBranchWriteSerializer, responses={200: OfficeBranchSerializer})
    def patch(self, request, branch_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = OfficeBranchWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        branch = update_branch(
            context=request.office_context,
            actor=request.user,
            request=request,
            branch_id=branch_id,
            data=serializer.validated_data,
        )
        branch = OfficeBranch.objects.select_related("location", "location__parent").get(pk=branch.pk)
        return Response(OfficeBranchSerializer(branch).data)


class OfficeStaffListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.staff.manage"

    @extend_schema(responses={200: MembershipSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = OfficeMembership.objects.filter(office=request.office_context.office).select_related(
            "user", "role", "branch"
        )
        return Response(MembershipSerializer(queryset, many=True).data)

    @extend_schema(request=StaffInviteSerializer, responses={200: MembershipSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = StaffInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = invite_staff(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        membership = OfficeMembership.objects.select_related("user", "role", "branch").get(pk=membership.pk)
        return Response(MembershipSerializer(membership).data)


class OfficeStaffDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.staff.manage"

    @extend_schema(request=StaffUpdateSerializer, responses={200: MembershipSerializer})
    def patch(self, request, membership_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        try:
            parsed_id = uuid.UUID(membership_id)
        except ValueError as exc:
            raise DomainAPIException("RESOURCE_NOT_FOUND") from exc
        serializer = StaffUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        membership = update_staff(
            context=request.office_context,
            actor=request.user,
            request=request,
            membership_id=parsed_id,
            data=serializer.validated_data,
        )
        membership = OfficeMembership.objects.select_related("user", "role", "branch").get(pk=membership.pk)
        return Response(MembershipSerializer(membership).data)


class OfficeVerificationView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.verification.manage"

    @extend_schema(responses={200: VerificationCaseSerializer})
    def get(self, request):  # type: ignore[no-untyped-def]
        case = latest_verification_case(request.office_context.office)
        case = VerificationCase.objects.prefetch_related("documents").get(pk=case.pk)
        return Response(VerificationCaseSerializer(case).data)


class OfficeVerificationCommandView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.verification.manage"

    @extend_schema(request=VerificationCommandSerializer, responses={200: VerificationCaseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = VerificationCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = str(serializer.validated_data["command"])
        if command not in {"submit", "resubmit"}:
            raise DomainAPIException("PERMISSION_DENIED")
        case = command_verification(
            office=request.office_context.office,
            actor=request.user,
            request=request,
            command=command,
            reason=serializer.validated_data.get("reason"),
            conditions=serializer.validated_data.get("conditions"),
        )
        case = VerificationCase.objects.prefetch_related("documents").get(pk=case.pk)
        return Response(VerificationCaseSerializer(case).data)


class OfficeVerificationDocumentListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.verification.manage"

    @extend_schema(responses={200: OfficeDocumentSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = OfficeDocument.objects.filter(office=request.office_context.office).order_by(
            "document_type", "-created_at"
        )
        return Response(OfficeDocumentSerializer(queryset, many=True).data)

    @extend_schema(request=OfficeDocumentWriteSerializer, responses={200: OfficeDocumentSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = OfficeDocumentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = register_office_document(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        return Response(OfficeDocumentSerializer(document).data)


class PlatformOfficeListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.office.verify"

    @extend_schema(responses={200: OfficeSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = Office.objects.select_related("operator").all().order_by("trade_name", "id")
        if status := request.query_params.get("status"):
            queryset = queryset.filter(status=status)
        if query := request.query_params.get("q", "").strip():
            queryset = queryset.filter(Q(legal_name__icontains=query) | Q(trade_name__icontains=query))
        return Response(OfficeSerializer(queryset[:200], many=True).data)


class PlatformOfficeVerificationCommandView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.office.verify"

    @extend_schema(request=VerificationCommandSerializer, responses={200: VerificationCaseSerializer})
    def post(self, request, office_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        office = Office.objects.filter(public_id=office_id).first()
        if office is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        serializer = VerificationCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = str(serializer.validated_data["command"])
        if command in {"submit", "resubmit"}:
            raise DomainAPIException("PERMISSION_DENIED")
        case = command_verification(
            office=office,
            actor=request.user,
            request=request,
            command=command,
            reason=serializer.validated_data.get("reason"),
            conditions=serializer.validated_data.get("conditions"),
        )
        case = VerificationCase.objects.prefetch_related("documents").get(pk=case.pk)
        return Response(VerificationCaseSerializer(case).data)


class PlatformOfficeDocumentReviewView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.office.verify"

    @extend_schema(request=OfficeDocumentReviewSerializer, responses={200: OfficeDocumentSerializer})
    def patch(self, request, office_id: str, document_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        office = Office.objects.filter(public_id=office_id).first()
        if office is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        try:
            parsed_document_id = uuid.UUID(document_id)
        except ValueError as exc:
            raise DomainAPIException("RESOURCE_NOT_FOUND") from exc
        serializer = OfficeDocumentReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = review_office_document(
            office=office,
            document_id=parsed_document_id,
            actor=request.user,
            request=request,
            status=str(serializer.validated_data["status"]),
            reason=serializer.validated_data.get("reason"),
        )
        return Response(OfficeDocumentSerializer(document).data)


class OfficePayoutAccountListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.payout.manage"

    @extend_schema(responses={200: PayoutAccountSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = OfficePayoutAccount.objects.filter(office=request.office_context.office).order_by("-created_at")
        return Response(PayoutAccountSerializer(queryset, many=True).data)

    @extend_schema(
        request=PayoutAccountWriteSerializer,
        responses={201: PayoutAccountSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = PayoutAccountWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = request_payout_account_change(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        return Response(PayoutAccountSerializer(account).data, status=201)


class OfficePayoutAccountApproveView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.payout.approve"

    @extend_schema(request=None, responses={200: PayoutAccountSerializer})
    def post(self, request, account_id: uuid.UUID):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        account = approve_payout_account_change(
            context=request.office_context,
            actor=request.user,
            request=request,
            account_id=account_id,
        )
        return Response(PayoutAccountSerializer(account).data)
