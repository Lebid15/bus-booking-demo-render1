from __future__ import annotations

import hashlib
import re
import uuid
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest

from auditlog.models import AuditLog

if TYPE_CHECKING:
    from identity.models import User

_SENSITIVE_FRAGMENTS = {
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "cookie",
    "session",
    "otp",
    "mfa_code",
    "verification_code",
    "cvv",
    "cvc",
    "card_number",
    "pan",
    "private_key",
    "client_secret",
    "api_key",
    "access_key",
}
_SAFE_KEYS = {"token_hash", "destination_hash", "ip_hash", "payload_hash", "sha256", "card_last4"}
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_CARD_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:\d[ -]?){13,19}(?![A-Za-z0-9])")


def _sensitive_key(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    if normalized in _SAFE_KEYS or normalized.endswith("_last4"):
        return False
    return any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS)


def _redact_string(value: str) -> str:
    value = _BEARER_PATTERN.sub("[REDACTED_BEARER]", value)
    value = _JWT_PATTERN.sub("[REDACTED_TOKEN]", value)
    return _CARD_PATTERN.sub("[REDACTED_CARD]", value)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if _sensitive_key(key) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _ip_hash(request: HttpRequest | None) -> bytes | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    return hashlib.sha256(ip.encode()).digest() if ip else None


def record_audit(
    *,
    action: str,
    object_type: str,
    actor_user: User | None = None,
    actor_type: str = "user",
    office_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
    request: HttpRequest | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason_code: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    raw_request_id = getattr(request, "request_id", None) if request else None
    request_id = uuid.UUID(raw_request_id) if raw_request_id else None
    return AuditLog.objects.create(
        actor_user=actor_user,
        actor_type=actor_type,
        office_id=office_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        request_id=request_id,
        ip_hash=_ip_hash(request),
        before_json=_redact(before),
        after_json=_redact(after),
        reason_code=reason_code,
        metadata=_redact(metadata or {}),
    )
