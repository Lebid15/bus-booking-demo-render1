from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auditlog.models import AuditLog
from auditlog.services import record_audit
from bookings.services import parse_hold_token
from finance.models import Commission
from identity.models import CustomerProfile, Role, User, UserSession
from organizations.models import Office, OfficeMembership
from securityops.models import DataSubjectRequest, LegalHold, RiskAssessment, StoredFile
from securityops.services import process_retention_requests

from .test_e13_policies_configuration import _bookable_trip, _booking_payload, _confirmed_booking, _hold

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.security]


def _user(label: str) -> User:
    return User.objects.create_user(
        full_name=label,
        email=f"{label.lower().replace(' ', '.')}-{uuid.uuid4().hex[:8]}@example.com",
        password="SecurePass!234",
    )


def _office(label: str) -> Office:
    return Office.objects.create(
        legal_name=f"{label} Legal",
        trade_name=label,
        office_type=Office.OfficeType.CARRIER,
        status=Office.Status.ACTIVE,
        support_phone="+963900000000",
    )


def _office_user(label: str, office: Office) -> User:
    user = _user(label)
    role = Role.objects.create(
        code=f"office.security.{uuid.uuid4().hex[:8]}",
        scope_type=Role.ScopeType.OFFICE,
        name_ar="موظف أمان",
    )
    OfficeMembership.objects.create(user=user, office=office, role=role)
    return user


def _recent_session(user: User) -> UserSession:
    return UserSession.objects.create(
        user=user,
        token_hash=uuid.uuid4().bytes + uuid.uuid4().bytes,
        expires_at=timezone.now() + timedelta(hours=1),
        mfa_verified_at=timezone.now(),
    )


def test_e14_ac01_cross_office_file_access_returns_generic_not_found_without_metadata(api_client: APIClient) -> None:
    office_a = _office("Office A")
    office_b = _office("Office B")
    user_a = _office_user("Employee A", office_a)
    user_b = _office_user("Employee B", office_b)

    api_client.force_authenticate(user_b)
    created = api_client.post(
        "/v1/files/upload-intents",
        {
            "purpose": "support_attachment",
            "filename": "evidence.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1024,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-file-office-b",
    )
    assert created.status_code == 200

    api_client.force_authenticate(user_a)
    denied = api_client.post(
        f"/v1/files/{created.data['file_id']}/complete",
        {"sha256": "a" * 64},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-cross-office-complete",
    )

    assert denied.status_code == 404
    assert denied.data["error"]["code"] == "RESOURCE_NOT_FOUND"
    serialized = json.dumps(denied.data, ensure_ascii=False)
    assert office_b.public_id not in serialized
    assert "count" not in serialized.lower()
    assert "owner" not in serialized.lower()


@override_settings(FILE_SCAN_MOCK_RESULT="malware")
def test_e14_ac02_malware_file_remains_quarantined_and_never_enters_final_storage(api_client: APIClient) -> None:
    user = _user("Upload Owner")
    api_client.force_authenticate(user)
    created = api_client.post(
        "/v1/files/upload-intents",
        {
            "purpose": "identity_document",
            "filename": "identity.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 4096,
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-malware-intent",
    )
    file_id = created.data["file_id"]

    completed = api_client.post(
        f"/v1/files/{file_id}/complete",
        {"sha256": "b" * 64},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-malware-complete",
    )

    assert completed.status_code == 422
    assert completed.data["error"]["code"] == "FILE_MALWARE_DETECTED"
    stored = StoredFile.objects.get(id=file_id)
    assert stored.scan_status == StoredFile.ScanStatus.REJECTED
    assert stored.object_key.startswith("quarantine/")
    assert not stored.object_key.startswith("private/")
    assert AuditLog.objects.filter(object_id=stored.id, reason_code="FILE_MALWARE_DETECTED").exists()


def test_e14_ac03_account_deletion_anonymizes_identity_and_preserves_booking_and_finance(
    api_client: APIClient,
) -> None:
    booking, _ = _confirmed_booking()
    user = _user("Privacy Customer")
    CustomerProfile.objects.create(
        user=user,
        date_of_birth=timezone.localdate() - timedelta(days=9000),
        nationality_code="SY",
        marketing_consent=True,
    )
    booking.customer_user = user
    booking.contact_name = user.full_name
    booking.contact_email = user.email
    booking.contact_phone = "+963944123456"
    booking.save(update_fields=["customer_user", "contact_name", "contact_email", "contact_phone", "updated_at"])
    commission_id = Commission.objects.get(booking=booking).id
    session = _recent_session(user)
    api_client.force_authenticate(user=user, token=session)

    response = api_client.post(
        "/v1/me/delete-account",
        {"confirmation": "DELETE"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-delete-account",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    booking.refresh_from_db()
    assert user.status == User.Status.DELETED
    assert user.full_name == "مستخدم محذوف"
    assert user.email is not None and user.email.endswith("@privacy.invalid")
    assert user.phone_e164 is None
    assert booking.contact_name == "مستخدم محذوف"
    assert booking.contact_email is None
    assert booking.total_amount > 0
    assert Commission.objects.filter(id=commission_id, booking=booking).exists()
    assert DataSubjectRequest.objects.get(id=response.data["request_id"]).status == DataSubjectRequest.Status.FULFILLED


def test_e14_ac04_retention_job_skips_legal_hold_and_audits_reason() -> None:
    user = _user("Held Customer")
    actor = User.objects.create_user(
        full_name="Legal Officer",
        email=f"legal-{uuid.uuid4().hex[:8]}@example.com",
        is_platform_staff=True,
    )
    request = DataSubjectRequest.objects.create(
        user=user,
        request_type=DataSubjectRequest.RequestType.DELETE,
        status=DataSubjectRequest.Status.SUBMITTED,
        due_at=timezone.now(),
    )
    hold = LegalHold.objects.create(
        subject_type=LegalHold.SubjectType.USER,
        subject_id=user.id,
        reason="نزاع مالي مفتوح يستوجب حفظ السجل",
        placed_by=actor,
    )

    result = process_retention_requests()

    request.refresh_from_db()
    user.refresh_from_db()
    assert result == {"processed": 0, "skipped_legal_hold": 1}
    assert request.status == DataSubjectRequest.Status.SUBMITTED
    assert str(hold.id) in str(request.decision_reason)
    assert user.status == User.Status.ACTIVE
    assert AuditLog.objects.filter(
        action="privacy.retention.skip",
        object_id=request.id,
        reason_code="LEGAL_HOLD_ACTIVE",
    ).exists()


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100, RISK_STEP_UP_CODE="123456")
def test_e14_ac05_medium_risk_requests_step_up_then_allows_verified_booking(api_client: APIClient) -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key=f"e14-risk-hold-{uuid.uuid4()}")
    payload = _booking_payload(trip, hold, passengers)
    payload["client_reference"] = "risk-50"

    first = api_client.post(
        "/v1/public/bookings",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-medium-risk-booking",
        HTTP_USER_AGENT="Risk Test Browser",
    )

    assert first.status_code == 403
    assert first.data["error"]["code"] == "AUTH_MFA_REQUIRED"
    challenge_id = first.data["error"]["details"]["challenge_id"]
    parsed_hold = parse_hold_token(str(hold["hold_token"]))
    assert parsed_hold is not None
    assessment = RiskAssessment.objects.get(subject_id=parsed_hold[0])
    assert assessment.decision == RiskAssessment.Decision.STEP_UP

    verified = api_client.post(
        f"/v1/public/risk-challenges/{challenge_id}/verify",
        {"code": "123456"},
        format="json",
    )
    assert verified.status_code == 200

    second = api_client.post(
        "/v1/public/bookings",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="e14-medium-risk-booking",
        HTTP_USER_AGENT="Risk Test Browser",
        HTTP_X_RISK_STEP_UP_TOKEN=verified.data["step_up_token"],
    )
    assert second.status_code == 200
    assert RiskAssessment.objects.filter(
        subject_id=assessment.subject_id,
        decision=RiskAssessment.Decision.ALLOW,
        review_status="verified",
    ).exists()


def test_e14_ac06_sensitive_audit_redacts_nested_secrets_tokens_cvv_and_card_numbers() -> None:
    event = record_audit(
        action="payment.sensitive.test",
        object_type="payment",
        actor_type="system",
        before={
            "card_number": "4111111111111111",
            "nested": {"cvv": "123", "authorization": "Bearer secret-token"},
        },
        after={
            "access_token": "eyJheader.payload.signature",
            "message": "received Bearer abc.def.ghi for card 5555 5555 5555 4444",
            "card_last4": "4444",
        },
        metadata={"client_secret": "super-secret", "sha256": "a" * 64},
    )

    serialized = json.dumps(
        {"before": event.before_json, "after": event.after_json, "metadata": event.metadata},
        ensure_ascii=False,
    )
    for secret in ("4111111111111111", "123", "secret-token", "super-secret", "5555 5555 5555 4444"):
        assert secret not in serialized
    assert event.after_json["card_last4"] == "4444"
    assert event.metadata["sha256"] == "a" * 64

@override_settings(
    APP_ENV="production",
    PRIVATE_UPLOAD_BASE_URL="https://upload.invalid",
    FILE_SCANNER_BACKEND="",
    RISK_STEP_UP_CODE="123456",
)
def test_e14_production_checks_reject_mock_storage_scanner_and_step_up_code() -> None:
    from django.core.checks import Tags, run_checks

    issue_ids = {issue.id for issue in run_checks(tags=[Tags.security], include_deployment_checks=True)}

    assert {"securityops.E001", "securityops.E002", "securityops.E004"}.issubset(issue_ids)


@override_settings(
    APP_ENV="production",
    PRIVATE_UPLOAD_BASE_URL="https://uploads.example.com/private",
    FILE_SCANNER_BACKEND="securityops.scanners._local_scanner",
    RISK_STEP_UP_CODE="849271",
)
def test_e14_production_checks_accept_explicit_deployment_contracts() -> None:
    from django.core.checks import Tags, run_checks

    issue_ids = {issue.id for issue in run_checks(tags=[Tags.security], include_deployment_checks=True)}

    assert not any(issue_id.startswith("securityops.") for issue_id in issue_ids)
