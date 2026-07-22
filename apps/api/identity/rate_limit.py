from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache


def _key(identifier: str, ip: str | None) -> str:
    digest = hashlib.sha256(f"{identifier}|{ip or 'unknown'}".encode()).hexdigest()
    return f"auth:login:{digest}"


def retry_after(identifier: str, ip: str | None) -> int:
    data = cache.get(_key(identifier, ip)) or {"failures": 0, "blocked_until": 0}
    from time import time

    remaining = int(data.get("blocked_until", 0) - time())
    return max(0, remaining)


def register_failure(identifier: str, ip: str | None) -> int:
    from time import time

    key = _key(identifier, ip)
    data = cache.get(key) or {"failures": 0, "blocked_until": 0}
    failures = int(data.get("failures", 0)) + 1
    blocked_for = 0
    if failures >= settings.LOGIN_RATE_LIMIT_THRESHOLD:
        exponent = failures - settings.LOGIN_RATE_LIMIT_THRESHOLD
        blocked_for = min(settings.LOGIN_RATE_LIMIT_BASE_SECONDS * (2**exponent), 900)
    payload = {"failures": failures, "blocked_until": int(time()) + blocked_for}
    cache.set(key, payload, timeout=3600)
    return blocked_for


def clear_failures(identifier: str, ip: str | None) -> None:
    cache.delete(_key(identifier, ip))
