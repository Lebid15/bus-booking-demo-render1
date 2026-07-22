from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone

from auditlog.models import AuditLog
from common.models import OutboxEvent
from identity.crypto import encrypt_secret
from identity.models import MfaMethod, Permission, Role, RolePermission, User, UserSession
from identity.normalization import normalize_phone
from identity.totp import generate_totp
from organizations.models import Office, OfficeMembership

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def make_user(*, email: str = "user@example.com", password: str = "SecurePass!234") -> User:
    return User.objects.create_user(full_name="مستخدم تجريبي", email=email, password=password)


def bearer(client, token: str) -> None:  # type: ignore[no-untyped-def]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")


@pytest.mark.django_db(transaction=True)
def test_e01_ac01_registration_normalizes_phone_and_prevents_duplicates(api_client):  # type: ignore[no-untyped-def]
    payload = {
        "full_name": "محمد أحمد",
        "phone": "٠٩٤٤ ١٢٣ ٤٥٦",
        "password": "StrongPassword!234",
    }
    response = api_client.post("/v1/auth/register", payload, format="json")
    assert response.status_code == 202
    user = User.objects.get(public_id=response.data["public_id"])
    assert user.phone_e164 == "+963944123456"
    assert user.status == User.Status.DISABLED
    assert OutboxEvent.objects.filter(
        aggregate_id=user.id, event_type="notification.requested"
    ).exists()

    duplicate = api_client.post("/v1/auth/register", payload, format="json")
    assert duplicate.status_code == 422
    assert duplicate.data["error"]["code"] == "VALIDATION_ERROR"

    verified = api_client.post(
        "/v1/auth/register/verify",
        {"challenge_id": response.data["challenge_id"], "code": "123456"},
        format="json",
    )
    assert verified.status_code == 200
    user.refresh_from_db()
    assert user.status == User.Status.ACTIVE
    assert user.phone_verified_at is not None
    assert AuditLog.objects.filter(
        actor_user=user, action="auth.registration.verify"
    ).exists()


def test_database_enforces_unique_normalized_email() -> None:
    make_user(email="person@example.com")
    with pytest.raises(IntegrityError):
        User.objects.create_user(
            full_name="Duplicate",
            email="person@example.com",
            password="SecurePass!234",
        )


def test_phone_normalization_supports_local_and_e164() -> None:
    assert normalize_phone("0944 123 456") == "+963944123456"
    assert normalize_phone("00963 944 123 456") == "+963944123456"
    assert normalize_phone("+963944123456") == "+963944123456"


def test_login_creates_revocable_server_side_session(api_client):  # type: ignore[no-untyped-def]
    user = make_user()
    response = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
        HTTP_X_DEVICE_FINGERPRINT="browser-1",
    )
    assert response.status_code == 200
    assert response.data["mfa_required"] is False
    session = UserSession.objects.get(id=response.data["session_id"])
    assert session.revoked_at is None
    assert session.device is not None

    bearer(api_client, response.data["access_token"])
    sessions = api_client.get("/v1/me/sessions")
    assert sessions.status_code == 200
    assert sessions.data[0]["current"] is True


@pytest.mark.security
def test_e01_ac03_revoked_session_is_rejected_immediately(api_client):  # type: ignore[no-untyped-def]
    user = make_user()
    login = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    )
    session = UserSession.objects.get(id=login.data["session_id"])
    session.revoked_at = timezone.now()
    session.save(update_fields=["revoked_at"])

    bearer(api_client, login.data["access_token"])
    response = api_client.get("/v1/me/sessions")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "AUTH_SESSION_EXPIRED"


@pytest.mark.security
def test_e01_ac02_sensitive_office_user_must_complete_mfa(api_client):  # type: ignore[no-untyped-def]
    user = make_user(email="owner@example.com")
    permission = Permission.objects.create(
        code="office.payment.confirm_manual",
        name_ar="تأكيد دفع يدوي",
        risk_level=Permission.RiskLevel.CRITICAL,
    )
    role = Role.objects.create(code="office.owner", scope_type="office", name_ar="مالك المكتب")
    RolePermission.objects.create(role=role, permission=permission)
    office = Office.objects.create(
        legal_name="مكتب الرقة للنقل",
        trade_name="الرقة للنقل",
        office_type=Office.OfficeType.GARAGE_OFFICE,
        status=Office.Status.ACTIVE,
        support_phone="+963900000000",
    )
    OfficeMembership.objects.create(user=user, office=office, role=role)
    secret = "JBSWY3DPEHPK3PXP"
    MfaMethod.objects.create(
        user=user,
        method_type=MfaMethod.MethodType.TOTP,
        secret_ciphertext=encrypt_secret(secret),
        verified_at=timezone.now(),
        is_primary=True,
    )

    login = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    )
    assert login.status_code == 403
    assert login.data["error"]["code"] == "AUTH_MFA_REQUIRED"
    assert UserSession.objects.filter(user=user).count() == 0

    challenge_id = login.data["error"]["details"]["challenge_id"]
    verify = api_client.post(
        "/v1/auth/mfa/verify",
        {"challenge_id": challenge_id, "code": generate_totp(secret)},
        format="json",
    )
    assert verify.status_code == 200
    assert UserSession.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    assert AuditLog.objects.filter(actor_user=user, action="auth.login.mfa").exists()


@override_settings(LOGIN_RATE_LIMIT_THRESHOLD=2, LOGIN_RATE_LIMIT_BASE_SECONDS=60)
@pytest.mark.security
def test_e01_ac04_progressive_rate_limit_is_generic(api_client):  # type: ignore[no-untyped-def]
    make_user()
    payload = {"identifier": "user@example.com", "password": "wrong-password"}
    assert api_client.post("/v1/auth/login", payload, format="json").status_code == 401
    assert api_client.post("/v1/auth/login", payload, format="json").status_code == 401
    limited = api_client.post("/v1/auth/login", payload, format="json")
    assert limited.status_code == 429
    assert limited.data["error"]["code"] == "RATE_LIMITED"
    assert "user" not in str(limited.data).lower()


def test_e01_ac05_revoking_one_session_keeps_other_active_and_audits(api_client):  # type: ignore[no-untyped-def]
    user = make_user()
    first = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    ).data
    second = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    ).data

    bearer(api_client, first["access_token"])
    response = api_client.delete(f"/v1/me/sessions/{second['session_id']}")
    assert response.status_code == 200
    assert UserSession.objects.get(id=second["session_id"]).revoked_at is not None
    assert UserSession.objects.get(id=first["session_id"]).revoked_at is None
    assert AuditLog.objects.filter(action="auth.session.revoke", actor_user=user).count() == 1
    assert api_client.get("/v1/me/sessions").status_code == 200


def test_expired_database_session_rejected_even_when_jwt_not_expired(api_client):  # type: ignore[no-untyped-def]
    user = make_user()
    login = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    ).data
    UserSession.objects.filter(id=login["session_id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
    bearer(api_client, login["access_token"])
    response = api_client.get("/v1/me/sessions")
    assert response.status_code == 401
    assert response.data["error"]["code"] == "AUTH_SESSION_EXPIRED"

@pytest.mark.security
def test_mfa_challenge_is_bound_to_request_ip(api_client):  # type: ignore[no-untyped-def]
    user = make_user(email="secure-owner@example.com")
    permission = Permission.objects.create(
        code="office.settlement.approve",
        name_ar="اعتماد تسوية",
        risk_level=Permission.RiskLevel.CRITICAL,
    )
    role = Role.objects.create(code="office.secure_owner", scope_type="office", name_ar="مالك حساس")
    RolePermission.objects.create(role=role, permission=permission)
    office = Office.objects.create(
        legal_name="مكتب أمان النقل",
        trade_name="أمان النقل",
        office_type=Office.OfficeType.GARAGE_OFFICE,
        status=Office.Status.ACTIVE,
        support_phone="+963900000001",
    )
    OfficeMembership.objects.create(user=user, office=office, role=role)
    secret = "JBSWY3DPEHPK3PXP"
    MfaMethod.objects.create(
        user=user,
        method_type=MfaMethod.MethodType.TOTP,
        secret_ciphertext=encrypt_secret(secret),
        verified_at=timezone.now(),
        is_primary=True,
    )

    login = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
        REMOTE_ADDR="10.20.30.40",
    )
    challenge_id = login.data["error"]["details"]["challenge_id"]
    verify = api_client.post(
        "/v1/auth/mfa/verify",
        {"challenge_id": challenge_id, "code": generate_totp(secret)},
        format="json",
        REMOTE_ADDR="10.20.30.41",
    )

    assert verify.status_code == 403
    assert verify.data["error"]["code"] == "AUTH_MFA_INVALID"
    assert UserSession.objects.filter(user=user).count() == 0
