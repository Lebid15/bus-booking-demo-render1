from __future__ import annotations

import uuid

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from common.exceptions import DomainAPIException
from identity.models import User, UserSession
from identity.tokens import decode_access_token


class SessionBearerAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):  # type: ignore[no-untyped-def]
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != self.keyword:
            raise DomainAPIException("AUTH_REQUIRED")
        try:
            payload = decode_access_token(header[1].decode())
            session_id = uuid.UUID(payload["sid"])
            user_id = uuid.UUID(payload["sub"])
        except (UnicodeDecodeError, ValueError, TypeError, KeyError) as exc:
            raise DomainAPIException("AUTH_SESSION_EXPIRED") from exc

        session = UserSession.objects.select_related("user", "device").filter(
            id=session_id,
            user_id=user_id,
        ).first()
        if session is None or session.revoked_at is not None or session.expires_at <= timezone.now():
            raise DomainAPIException("AUTH_SESSION_EXPIRED")
        if session.user.status != User.Status.ACTIVE:
            raise DomainAPIException("AUTH_ACCOUNT_SUSPENDED")
        return session.user, session

    def authenticate_header(self, request):  # type: ignore[no-untyped-def]
        return "Bearer"
