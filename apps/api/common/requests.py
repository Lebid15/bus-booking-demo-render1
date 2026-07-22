from __future__ import annotations

from django.http import HttpRequest

from common.exceptions import DomainAPIException


def require_idempotency_key(request: HttpRequest) -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not 8 <= len(key) <= 120:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "Idempotency-Key", "reason": "required_length_8_120"}],
        )
    return key


def parse_version(value: object) -> int:
    try:
        version = int(str(value))
    except (TypeError, ValueError) as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "version", "reason": "integer_required"}],
        ) from exc
    if version < 1:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "version", "reason": "must_be_positive"}],
        )
    return version
