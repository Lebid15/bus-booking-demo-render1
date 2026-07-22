from __future__ import annotations

import uuid

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from identity.serializers import (
    LoginSerializer,
    MfaVerifySerializer,
    RegisterSerializer,
    RegistrationVerifySerializer,
    SessionSerializer,
)
from identity.services import (
    login,
    revoke_session,
    start_customer_registration,
    verify_customer_registration,
    verify_mfa_challenge,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={202: dict})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = start_customer_registration(**serializer.validated_data)
        return Response(
            {
                "public_id": result.user.public_id,
                "challenge_id": result.challenge_id,
                "verification_required": True,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RegistrationVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegistrationVerifySerializer, responses={200: dict})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = RegistrationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = verify_customer_registration(request=request, **serializer.validated_data)
        return Response({"public_id": user.public_id, "verified": True})


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses={200: dict})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = login(request=request, **serializer.validated_data)
        if result.mfa_required:
            raise DomainAPIException(
                "AUTH_MFA_REQUIRED",
                details={
                    "challenge_id": result.challenge_id,
                    "expires_in": 300,
                    "supported_methods": ["totp"],
                },
            )
        if result.tokens is None:
            raise RuntimeError("Login result did not contain tokens")
        return Response({**result.tokens, "mfa_required": False})


class MfaVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=MfaVerifySerializer, responses={200: dict})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = MfaVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tokens = verify_mfa_challenge(request=request, **serializer.validated_data)
        return Response(tokens)


class SessionListView(APIView):
    @extend_schema(responses={200: SessionSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        sessions = request.user.sessions.select_related("device").order_by("-created_at")
        serializer = SessionSerializer(
            sessions,
            many=True,
            context={"current_session": request.auth},
        )
        return Response(serializer.data)


class SessionRevokeView(APIView):
    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def delete(self, request, session_id: uuid.UUID):  # type: ignore[no-untyped-def]
        session = revoke_session(request=request, actor=request.user, session_id=session_id)
        return Response({"id": str(session.id), "revoked": True})
