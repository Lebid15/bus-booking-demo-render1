from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.requests import require_idempotency_key
from organizations.permissions import HasPlatformAccess
from securityops.models import LegalHold
from securityops.serializers import (
    AccountDeletionRequestSerializer,
    DataSubjectResponseSerializer,
    LegalHoldCreateSerializer,
    LegalHoldReleaseSerializer,
    LegalHoldSerializer,
    RiskAssessmentSerializer,
    RiskChallengeResponseSerializer,
    RiskChallengeVerifySerializer,
    UploadCompleteRequestSerializer,
    UploadCompleteResponseSerializer,
    UploadIntentRequestSerializer,
    UploadIntentResponseSerializer,
)
from securityops.services import (
    complete_upload,
    create_upload_intent,
    list_risk_assessments,
    place_legal_hold,
    release_legal_hold,
    request_account_deletion,
    request_data_export,
    serialize_legal_hold,
    verify_risk_challenge,
)


class UploadIntentView(APIView):
    @extend_schema(request=UploadIntentRequestSerializer, responses={200: UploadIntentResponseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = UploadIntentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = create_upload_intent(
            user=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            data=dict(serializer.validated_data),
        )
        return Response(UploadIntentResponseSerializer(response).data)


class UploadCompleteView(APIView):
    @extend_schema(request=UploadCompleteRequestSerializer, responses={200: UploadCompleteResponseSerializer})
    def post(self, request, file_id: uuid.UUID):  # type: ignore[no-untyped-def]
        serializer = UploadCompleteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = complete_upload(
            user=request.user,
            request=request,
            file_id=file_id,
            idempotency_key=require_idempotency_key(request),
            sha256=str(serializer.validated_data["sha256"]),
        )
        return Response(UploadCompleteResponseSerializer(response).data)


class MyDataExportView(APIView):
    @extend_schema(request=None, responses={200: DataSubjectResponseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        response = request_data_export(
            user=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
        )
        return Response(DataSubjectResponseSerializer(response).data)


class MyAccountDeletionView(APIView):
    @extend_schema(request=AccountDeletionRequestSerializer, responses={200: DataSubjectResponseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = AccountDeletionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = request_account_deletion(
            user=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            confirmation=str(serializer.validated_data["confirmation"]),
        )
        return Response(DataSubjectResponseSerializer(response).data)


class RiskChallengeVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=RiskChallengeVerifySerializer, responses={200: RiskChallengeResponseSerializer})
    def post(self, request, challenge_id: uuid.UUID):  # type: ignore[no-untyped-def]
        serializer = RiskChallengeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = verify_risk_challenge(
            challenge_id=challenge_id,
            code=str(serializer.validated_data["code"]),
            request=request,
        )
        return Response(RiskChallengeResponseSerializer(response).data)


class PlatformRiskAssessmentListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.risk.view"

    @extend_schema(
        parameters=[
            OpenApiParameter("decision", str, required=False),
            OpenApiParameter("subject_type", str, required=False),
        ],
        responses={200: RiskAssessmentSerializer(many=True)},
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        response = list_risk_assessments(
            decision=request.query_params.get("decision"),
            subject_type=request.query_params.get("subject_type"),
        )
        return Response(RiskAssessmentSerializer(response, many=True).data)  # type: ignore[arg-type]


class PlatformLegalHoldListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.privacy.manage"

    @extend_schema(responses={200: LegalHoldSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        rows = [serialize_legal_hold(item) for item in LegalHold.objects.all().order_by("-placed_at")[:200]]
        return Response(LegalHoldSerializer(rows, many=True).data)  # type: ignore[arg-type]

    @extend_schema(request=LegalHoldCreateSerializer, responses={200: LegalHoldSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = LegalHoldCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = place_legal_hold(
            actor=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            data=dict(serializer.validated_data),
        )
        return Response(LegalHoldSerializer(response).data)


class PlatformLegalHoldReleaseView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.privacy.manage"

    @extend_schema(request=LegalHoldReleaseSerializer, responses={200: LegalHoldSerializer})
    def post(self, request, hold_id: uuid.UUID):  # type: ignore[no-untyped-def]
        serializer = LegalHoldReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = release_legal_hold(
            actor=request.user,
            request=request,
            hold_id=hold_id,
            idempotency_key=require_idempotency_key(request),
            reason=str(serializer.validated_data["reason"]),
        )
        return Response(LegalHoldSerializer(response).data)
