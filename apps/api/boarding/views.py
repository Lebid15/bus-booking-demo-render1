from __future__ import annotations

from typing import Any, cast

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from boarding.serializers import (
    BoardingCommandSerializer,
    BoardingResultSerializer,
    OfflinePackageResponseSerializer,
    OfflineSyncResponseSerializer,
    OfflineSyncSerializer,
)
from boarding.services import (
    create_offline_package,
    execute_boarding_command,
    get_manifest,
    serialize_manifest,
    sync_offline_events,
)
from common.requests import require_idempotency_key
from identity.models import UserSession
from organizations.permissions import HasOfficeContext

IDEMPOTENCY_PARAMETER = OpenApiParameter(
    name="Idempotency-Key",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="مفتاح فريد من 8 إلى 120 محرفًا لإعادة المحاولة الآمنة.",
)


class OfficeBoardingCommandView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.boarding.scan"

    @extend_schema(
        operation_id="boardingCommand",
        summary="تنفيذ أمر صعود",
        tags=["Boarding"],
        parameters=[IDEMPOTENCY_PARAMETER],
        request=BoardingCommandSerializer,
        responses={200: BoardingResultSerializer},
    )
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        idempotency_key = require_idempotency_key(request)
        serializer = BoardingCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = request.auth if isinstance(request.auth, UserSession) else None
        result = execute_boarding_command(
            context=request.office_context,
            actor=request.user,
            session=session,
            request=request,
            trip_id=trip_id,
            data=cast(dict[str, Any], serializer.validated_data),
            idempotency_key=idempotency_key,
        )
        return Response(BoardingResultSerializer(result).data)


class OfficeManifestView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.boarding.scan"

    @extend_schema(
        operation_id="getManifest",
        summary="قائمة ركاب الرحلة",
        tags=["Boarding"],
        responses={200: dict[str, Any]},
        parameters=[OpenApiParameter("version", str, required=False)],
    )
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        manifest = get_manifest(
            context=request.office_context,
            trip_id=trip_id,
            version=request.query_params.get("version"),
        )
        return Response(serialize_manifest(manifest))


class OfficeOfflinePackageView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.boarding.scan"

    @extend_schema(
        operation_id="createOfflinePackage",
        summary="توليد حزمة صعود دون اتصال",
        tags=["Boarding"],
        parameters=[IDEMPOTENCY_PARAMETER],
        request=None,
        responses={200: OfflinePackageResponseSerializer},
    )
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        idempotency_key = require_idempotency_key(request)
        session = request.auth if isinstance(request.auth, UserSession) else None
        result = create_offline_package(
            context=request.office_context,
            actor=request.user,
            session=session,
            request=request,
            trip_id=trip_id,
            idempotency_key=idempotency_key,
        )
        return Response(OfflinePackageResponseSerializer(result).data)


class OfficeOfflineSyncView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.boarding.scan"

    @extend_schema(
        operation_id="syncOfflineBoarding",
        summary="مزامنة أحداث الصعود غير المتصلة",
        tags=["Boarding"],
        parameters=[IDEMPOTENCY_PARAMETER],
        request=OfflineSyncSerializer,
        responses={200: OfflineSyncResponseSerializer},
    )
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        idempotency_key = require_idempotency_key(request)
        serializer = OfflineSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = request.auth if isinstance(request.auth, UserSession) else None
        result = sync_offline_events(
            context=request.office_context,
            actor=request.user,
            session=session,
            request=request,
            trip_id=trip_id,
            package_hash=str(serializer.validated_data["package_hash"]),
            events=cast(list[dict[str, Any]], serializer.validated_data["events"]),
            idempotency_key=idempotency_key,
        )
        return Response(OfflineSyncResponseSerializer(result).data)
