from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import jwt
from django.conf import settings
from django.utils import timezone

from identity.models import User, UserDevice, UserSession


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def issue_session(
    *,
    user: User,
    device: UserDevice | None,
    ip_hash: bytes | None,
    user_agent: str | None,
    mfa_verified: bool = False,
) -> dict[str, Any]:
    now = timezone.now()
    refresh_token = secrets.token_urlsafe(48)
    session = UserSession.objects.create(
        user=user,
        token_hash=hash_token(refresh_token),
        device=device,
        ip_hash=ip_hash,
        user_agent=(user_agent or "")[:1000],
        expires_at=now + timedelta(seconds=settings.SESSION_MAX_TTL_SECONDS),
        mfa_verified_at=now if mfa_verified else None,
    )
    access_exp = now + timedelta(seconds=settings.JWT_ACCESS_TTL_SECONDS)
    access_token = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(session.id),
            "typ": "access",
            "iat": int(now.timestamp()),
            "exp": int(access_exp.timestamp()),
        },
        settings.JWT_SIGNING_KEY,
        algorithm="HS256",
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",  # nosec B105 - OAuth token type
        "expires_in": settings.JWT_ACCESS_TTL_SECONDS,
        "session_id": str(session.id),
    }


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise ValueError("invalid token") from exc
    if payload.get("typ") != "access" or not payload.get("sid") or not payload.get("sub"):
        raise ValueError("invalid token type")
    return payload
