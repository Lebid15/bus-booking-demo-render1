from __future__ import annotations

from collections.abc import Callable

from django.db import DatabaseError, OperationalError
from django.http import HttpRequest, HttpResponse, JsonResponse

from continuity.models import PlatformContinuityState

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_ALLOWED_PREFIXES = (
    "/health/",
    "/v1/platform/continuity",
    "/v1/platform/releases",
    "/v1/platform/incidents",
    "/v1/platform/load-tests",
)


class ContinuityWriteGuardMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            if request.method in _WRITE_METHODS and not request.path.startswith(_ALLOWED_PREFIXES):
                state = PlatformContinuityState.objects.filter(singleton_key="platform").only("mode").first()
                if state is not None and state.mode != PlatformContinuityState.Mode.NORMAL:
                    return JsonResponse(
                        {
                            "error": {
                                "code": "PLATFORM_MAINTENANCE",
                                "message": "المنصة في وضع الصيانة الآمنة",
                                "retryable": True,
                                "details": [],
                            }
                        },
                        status=503,
                    )
            return self.get_response(request)
        except (OperationalError, DatabaseError):
            return JsonResponse(
                {
                    "error": {
                        "code": "DATABASE_UNAVAILABLE",
                        "message": "قاعدة البيانات غير متاحة مؤقتًا",
                        "retryable": True,
                        "details": [],
                    }
                },
                status=503,
            )
