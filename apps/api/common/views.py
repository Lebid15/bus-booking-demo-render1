from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from common.serializers import LiveHealthSerializer, ReadyHealthSerializer
from continuity.models import PlatformContinuityState


@extend_schema(responses={200: LiveHealthSerializer}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
def live(request):  # type: ignore[no-untyped-def]
    return Response({"status": "ok", "service": "bus-booking-api"})


@extend_schema(responses={200: ReadyHealthSerializer, 503: ReadyHealthSerializer}, auth=[])
@api_view(["GET"])
@permission_classes([AllowAny])
def ready(request):  # type: ignore[no-untyped-def]
    checks: dict[str, str] = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    checks["database"] = "ok"
    cache.set("health:ready", "ok", timeout=5)
    checks["cache"] = "ok" if cache.get("health:ready") == "ok" else "failed"
    state = PlatformContinuityState.objects.filter(singleton_key="platform").only("mode").first()
    checks["continuity"] = "ok" if state is None or state.mode == PlatformContinuityState.Mode.NORMAL else state.mode
    status_code = 200 if all(value == "ok" for value in checks.values()) else 503
    return Response({"status": "ok" if status_code == 200 else "degraded", "checks": checks}, status=status_code)
