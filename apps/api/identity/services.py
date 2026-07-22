from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from identity.crypto import decrypt_secret
from identity.models import MfaMethod, Permission, User, UserDevice, UserSession
from identity.normalization import normalize_email, normalize_identifier, normalize_phone
from identity.rate_limit import clear_failures, register_failure, retry_after
from identity.tokens import issue_session
from identity.totp import verify_totp


@dataclass(frozen=True)
class LoginResult:
    tokens: dict[str, Any] | None = None
    challenge_id: str | None = None
    mfa_required: bool = False


@dataclass(frozen=True)
class RegistrationResult:
    user: User
    challenge_id: str


def request_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def request_ip_hash(request: HttpRequest) -> bytes | None:
    ip = request_ip(request)
    return hashlib.sha256(ip.encode()).digest() if ip else None


def _verification_code_hash(challenge_id: str, code: str) -> str:
    raw = f"{challenge_id}:{code}:{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()


@transaction.atomic
def start_customer_registration(
    *, full_name: str, password: str, email: str | None = None, phone: str | None = None
) -> RegistrationResult:
    user = create_customer_account(
        full_name=full_name,
        password=password,
        email=email,
        phone=phone,
        status=User.Status.DISABLED,
    )
    challenge_id = secrets.token_urlsafe(32)
    code = (
        settings.DEV_VERIFICATION_CODE
        if settings.APP_ENV in {"local", "test", "ci"}
        else str(secrets.randbelow(900000) + 100000)
    )
    identifier_type = "email" if user.email else "phone"
    challenge_payload = {
        "user_id": str(user.id),
        "identifier_type": identifier_type,
        "code_hash": _verification_code_hash(challenge_id, code),
        "attempts": 0,
    }
    OutboxEvent.objects.create(
        aggregate_type="user",
        aggregate_id=user.id,
        event_type="notification.requested",
        payload={
            "template": "account_verification",
            "channel": identifier_type,
            "user_id": str(user.id),
            "challenge_id": challenge_id,
        },
    )
    transaction.on_commit(
        lambda: cache.set(
            f"registration:challenge:{challenge_id}",
            challenge_payload,
            timeout=settings.REGISTRATION_CHALLENGE_TTL_SECONDS,
        )
    )
    return RegistrationResult(user=user, challenge_id=challenge_id)


@transaction.atomic
def verify_customer_registration(
    *, request: HttpRequest, challenge_id: str, code: str
) -> User:
    key = f"registration:challenge:{challenge_id}"
    challenge = cache.get(key)
    if not challenge:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "code", "reason": "invalid_or_expired"}],
        )
    if int(challenge.get("attempts", 0)) >= 5:
        cache.delete(key)
        raise DomainAPIException("RATE_LIMITED", details={"reason": "verification_attempts_exceeded"})
    expected = challenge["code_hash"]
    actual = _verification_code_hash(challenge_id, code)
    if not secrets.compare_digest(expected, actual):
        challenge["attempts"] = int(challenge.get("attempts", 0)) + 1
        cache.set(key, challenge, timeout=settings.REGISTRATION_CHALLENGE_TTL_SECONDS)
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "code", "reason": "invalid_or_expired"}],
        )
    user = User.objects.select_for_update().filter(
        id=challenge["user_id"], status=User.Status.DISABLED
    ).first()
    if user is None:
        raise DomainAPIException("VALIDATION_ERROR")
    now = timezone.now()
    user.status = User.Status.ACTIVE
    fields = ["status", "updated_at"]
    if challenge["identifier_type"] == "email":
        user.email_verified_at = now
        fields.append("email_verified_at")
    else:
        user.phone_verified_at = now
        fields.append("phone_verified_at")
    user.save(update_fields=fields)
    cache.delete(key)
    record_audit(
        action="auth.registration.verify",
        object_type="user",
        object_id=user.id,
        actor_user=user,
        request=request,
        metadata={"identifier_type": challenge["identifier_type"]},
    )
    return user


def create_customer_account(
    *,
    full_name: str,
    password: str,
    email: str | None = None,
    phone: str | None = None,
    status: str = User.Status.ACTIVE,
) -> User:
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)
    if not normalized_email and not normalized_phone:
        raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "identifier", "reason": "required"}])
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                full_name=full_name,
                password=password,
                email=normalized_email,
                phone_e164=normalized_phone,
                status=status,
            )
            from identity.models import CustomerProfile

            CustomerProfile.objects.create(user=user)
            return user
    except IntegrityError as exc:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "identifier", "reason": "already_used"}],
        ) from exc


def user_requires_mfa(user: User) -> bool:
    if settings.APP_ENV == "local" and getattr(settings, "DEMO_MODE", False):
        return False
    if user.is_platform_staff:
        return True
    from organizations.models import OfficeMembership

    return OfficeMembership.objects.filter(user=user,
        status="active",
        revoked_at__isnull=True,
        role__permissions__risk_level__in=[Permission.RiskLevel.SENSITIVE, Permission.RiskLevel.CRITICAL],
    ).exists()


def _get_or_create_device(request: HttpRequest, user: User) -> UserDevice | None:
    raw = request.headers.get("X-Device-Fingerprint")
    if not raw:
        return None
    digest = hashlib.sha256(raw.encode()).digest()
    device, _ = UserDevice.objects.get_or_create(
        user=user,
        device_fingerprint_hash=digest,
        defaults={"label": request.headers.get("X-Device-Label", "")[:120]},
    )
    return device


def _complete_login(*, request: HttpRequest, user: User, mfa: bool) -> dict[str, Any]:
    device = _get_or_create_device(request, user)
    tokens = issue_session(
        user=user,
        device=device,
        ip_hash=request_ip_hash(request),
        user_agent=request.headers.get("User-Agent"),
        mfa_verified=mfa,
    )
    User.objects.filter(pk=user.pk).update(last_login_at=timezone.now())
    record_audit(
        action="auth.login.mfa" if mfa else "auth.login",
        object_type="user_session",
        object_id=uuid.UUID(tokens["session_id"]),
        actor_user=user,
        request=request,
        metadata={"mfa": mfa, "device_id": str(device.id) if device else None},
    )
    memberships = list(
        user.office_memberships.filter(status="active", revoked_at__isnull=True)
        .select_related("office")[:2]
    )
    landing_path = "/platform" if user.is_platform_staff else ("/office" if len(memberships) == 1 else "/")
    tokens["user"] = {
        "id": user.public_id,
        "full_name": user.full_name,
        "email": user.email,
        "is_platform_staff": user.is_platform_staff,
        "office": (
            {"id": memberships[0].office.public_id, "name": memberships[0].office.trade_name}
            if len(memberships) == 1
            else None
        ),
    }
    tokens["landing_path"] = landing_path
    return tokens


def login(*, request: HttpRequest, identifier: str, password: str) -> LoginResult:
    kind, normalized = normalize_identifier(identifier)
    ip = request_ip(request)
    wait = retry_after(normalized, ip)
    if wait:
        raise DomainAPIException("RATE_LIMITED", details={"retry_after_seconds": wait})

    user = User.objects.filter(**{kind: normalized}).first()
    if user is None or not user.check_password(password):
        blocked_for = register_failure(normalized, ip)
        details: dict[str, Any] | list[dict[str, Any]] = (
            {"retry_after_seconds": blocked_for} if blocked_for else []
        )
        raise DomainAPIException("AUTH_INVALID_CREDENTIALS", details=details)
    if not user.is_active:
        raise DomainAPIException("AUTH_ACCOUNT_SUSPENDED")
    clear_failures(normalized, ip)

    if user_requires_mfa(user):
        if not user.mfa_methods.filter(verified_at__isnull=False, disabled_at__isnull=True).exists():
            raise DomainAPIException(
                "AUTH_MFA_REQUIRED",
                details={"reason": "mfa_enrollment_required"},
                retryable=False,
            )
        challenge_id = secrets.token_urlsafe(32)
        ip_hash = request_ip_hash(request)
        cache.set(
            f"mfa:challenge:{challenge_id}",
            {"user_id": str(user.id), "ip_hash": ip_hash.hex() if ip_hash else None},
            timeout=settings.MFA_CHALLENGE_TTL_SECONDS,
        )
        return LoginResult(challenge_id=challenge_id, mfa_required=True)

    return LoginResult(tokens=_complete_login(request=request, user=user, mfa=False))


def verify_mfa_challenge(*, request: HttpRequest, challenge_id: str, code: str) -> dict[str, Any]:
    key = f"mfa:challenge:{challenge_id}"
    challenge = cache.get(key)
    if not challenge:
        raise DomainAPIException("AUTH_MFA_INVALID")
    current_ip_hash = request_ip_hash(request)
    if challenge.get("ip_hash") != (current_ip_hash.hex() if current_ip_hash else None):
        raise DomainAPIException("AUTH_MFA_INVALID")
    user = User.objects.filter(pk=challenge["user_id"], status=User.Status.ACTIVE).first()
    if user is None:
        raise DomainAPIException("AUTH_MFA_INVALID")

    valid = False
    methods = MfaMethod.objects.filter(
        user=user,
        method_type=MfaMethod.MethodType.TOTP,
        verified_at__isnull=False,
        disabled_at__isnull=True,
    )
    for method in methods:
        if method.secret_ciphertext and verify_totp(decrypt_secret(bytes(method.secret_ciphertext)), code):
            valid = True
            break
    if not valid:
        raise DomainAPIException("AUTH_MFA_INVALID")
    cache.delete(key)
    return _complete_login(request=request, user=user, mfa=True)


@transaction.atomic
def revoke_session(*, request: HttpRequest, actor: User, session_id: uuid.UUID) -> UserSession:
    session = UserSession.objects.select_for_update().filter(id=session_id, user=actor).first()
    if session is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        record_audit(
            action="auth.session.revoke",
            object_type="user_session",
            object_id=session.id,
            actor_user=actor,
            request=request,
        )
    return session
