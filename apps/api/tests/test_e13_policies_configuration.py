from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from auditlog.models import AuditLog
from bookings.models import Booking
from bookings.services import create_public_booking
from common.exceptions import DomainAPIException
from identity.models import User, UserSession
from policies.models import ConfigurationValue, PolicyAcceptance, PolicyVersion
from policies.services import (
    approve_configuration_changes,
    create_policy_version,
    effective_configuration,
    propose_configuration_changes,
)

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import _booking_payload, _hold

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _mfa_request(user: User, *, key: str, path: str = "/v1/platform/configuration"):
    request = RequestFactory().patch(
        path,
        data={},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=key,
        HTTP_USER_AGENT="E13 integration test agent",
        REMOTE_ADDR="203.0.113.88",
    )
    request.user = user
    request.auth = UserSession.objects.create(
        user=user,
        token_hash=f"e13-{uuid.uuid4()}".encode(),
        expires_at=timezone.now() + timedelta(hours=2),
        mfa_verified_at=timezone.now(),
    )
    return request


def _platform_user(label: str) -> User:
    return User.objects.create_user(
        full_name=label,
        email=f"{label.lower().replace(' ', '.')}-{uuid.uuid4().hex[:6]}@example.com",
        is_platform_staff=True,
    )


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def _confirmed_booking() -> tuple[Booking, dict[str, object]]:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key=f"e13-hold-{uuid.uuid4()}")
    payload = _booking_payload(trip, hold, passengers)
    result = create_public_booking(
        payload=payload,
        idempotency_key=f"e13-booking-{uuid.uuid4()}",
        request=_request(key=f"e13-request-{uuid.uuid4()}"),
    )
    return Booking.objects.get(public_id=result["id"]), payload


def test_e13_ac01_office_configuration_outside_platform_bounds_is_rejected() -> None:
    trip = _bookable_trip()
    actor = trip.created_by
    request = _mfa_request(actor, key="e13-office-out-of-range", path="/v1/office/configuration")

    with pytest.raises(DomainAPIException) as exc:
        propose_configuration_changes(
            scope_type=ConfigurationValue.ScopeType.OFFICE,
            scope_id=trip.office_id,
            actor=actor,
            request=request,
            changes={"office.boarding.open_minutes": 181},
            reason="اختبار حدود المنصة",
            effective_from=timezone.now(),
            idempotency_key="e13-office-out-of-range",
            auto_approve=True,
        )

    assert exc.value.code == "CONFIGURATION_OUT_OF_RANGE"
    assert not ConfigurationValue.objects.filter(scope_id=trip.office_id).exists()


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e13_ac02_future_policy_does_not_change_existing_booking_snapshot() -> None:
    booking, _ = _confirmed_booking()
    frozen = dict(booking.policy_snapshot)
    current = PolicyVersion.objects.get(id=booking.terms_version_ids[0])
    actor = _platform_user("Policy Publisher")
    future_at = timezone.now() + timedelta(days=3)

    policy, _ = create_policy_version(
        actor=actor,
        request=_mfa_request(actor, key="e13-future-policy", path="/v1/platform/policies"),
        idempotency_key="e13-future-policy",
        data={
            "code": current.template.code,
            "policy_type": current.template.policy_type,
            "owner_scope": current.template.owner_scope,
            "office_id": current.office.public_id if current.office else None,
            "language": current.language,
            "title": "إصدار مستقبلي",
            "content_markdown": "سياسة مستقبلية لا تطبق بأثر رجعي.",
            "rules_json": {"future": True},
            "effective_from": future_at,
            "effective_to": None,
            "publish": True,
        },
    )

    booking.refresh_from_db()
    assert policy.version_no == current.version_no + 1
    assert policy.effective_from == future_at
    assert booking.policy_snapshot == frozen
    assert str(policy.id) not in booking.terms_version_ids


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e13_ac03_missing_required_policy_acceptance_blocks_confirmation() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key="e13-missing-policy-hold")
    payload = _booking_payload(trip, hold, passengers)
    accepted = list(payload["accepted_policy_version_ids"])
    payload["accepted_policy_version_ids"] = accepted[:-1]

    with pytest.raises(DomainAPIException) as exc:
        create_public_booking(
            payload=payload,
            idempotency_key="e13-missing-policy-booking",
            request=_request(key="e13-missing-policy-booking"),
        )

    assert exc.value.code == "POLICY_ACCEPTANCE_REQUIRED"
    assert Booking.objects.count() == 0


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e13_ac04_acceptance_records_version_language_time_and_booking_without_raw_secrets() -> None:
    booking, _ = _confirmed_booking()
    acceptances = list(
        PolicyAcceptance.objects.select_related("policy_version").filter(
            subject_type=PolicyAcceptance.SubjectType.BOOKING,
            subject_id=booking.id,
        )
    )

    assert len(acceptances) == len(booking.terms_version_ids)
    assert {str(item.policy_version_id) for item in acceptances} == set(booking.terms_version_ids)
    assert {item.policy_version.language for item in acceptances} == {"ar"}
    assert all(item.accepted_at is not None for item in acceptances)
    assert all(item.ip_hash is not None and bytes(item.ip_hash) != b"203.0.113.10" for item in acceptances)
    assert all(item.user_agent_hash is None for item in acceptances)


@override_settings(SENSITIVE_MFA_MAX_AGE_SECONDS=900)
def test_e13_ac05_sensitive_platform_change_requires_second_approver_and_audits_before_after_reason() -> None:
    proposer = _platform_user("Configuration Proposer")
    approver = _platform_user("Configuration Approver")
    effective_at = timezone.now() + timedelta(minutes=5)
    rows = propose_configuration_changes(
        scope_type=ConfigurationValue.ScopeType.PLATFORM,
        scope_id=None,
        actor=proposer,
        request=_mfa_request(proposer, key="e13-platform-propose"),
        changes={"platform.risk.manual_review_threshold": 75},
        reason="رفع مستوى المراجعة اليدوية",
        effective_from=effective_at,
        idempotency_key="e13-platform-propose",
        auto_approve=False,
    )
    row = rows[0]
    assert row.approved_by_id is None
    assert effective_configuration(scope_type=ConfigurationValue.ScopeType.PLATFORM)[
        "platform.risk.manual_review_threshold"
    ]["value"] == 50

    with pytest.raises(DomainAPIException) as exc:
        approve_configuration_changes(
            actor=proposer,
            request=_mfa_request(proposer, key="e13-self-approve"),
            change_ids=[row.id],
            reason="اعتماد ذاتي",
            idempotency_key="e13-self-approve",
        )
    assert exc.value.code == "DUAL_APPROVAL_REQUIRED"

    approved = approve_configuration_changes(
        actor=approver,
        request=_mfa_request(approver, key="e13-platform-approve"),
        change_ids=[row.id],
        reason="اعتماد التعديل بعد المراجعة",
        idempotency_key="e13-platform-approve",
    )[0]
    assert approved.approved_by_id == approver.id

    audit = AuditLog.objects.get(action="platform.configuration.approve", object_id=row.id)
    assert audit.actor_user_id == approver.id
    assert audit.before_json == {"key": row.key, "value": 50}
    assert audit.after_json["key"] == row.key
    assert audit.after_json["value"] == 75
    assert audit.after_json["effective_from"] == row.effective_from.isoformat()
    assert audit.reason_code == "اعتماد التعديل بعد المراجعة"
    assert audit.metadata["created_by"] == str(proposer.id)
    assert audit.metadata["approved_by"] == str(approver.id)


def test_e13_configuration_snapshot_is_frozen_when_trip_is_scheduled() -> None:
    trip = _bookable_trip()
    snapshot = dict(trip.pricing_snapshot["configuration"])
    assert snapshot["office.boarding.open_minutes"]["value"] == 60

    propose_configuration_changes(
        scope_type=ConfigurationValue.ScopeType.OFFICE,
        scope_id=trip.office_id,
        actor=trip.created_by,
        request=_mfa_request(
            trip.created_by,
            key="e13-office-snapshot-change",
            path="/v1/office/configuration",
        ),
        changes={"office.boarding.open_minutes": 90},
        reason="تغيير الرحلات الجديدة فقط",
        effective_from=timezone.now(),
        idempotency_key="e13-office-snapshot-change",
        auto_approve=True,
    )

    trip.refresh_from_db()
    assert trip.pricing_snapshot["configuration"] == snapshot
    current = effective_configuration(
        scope_type=ConfigurationValue.ScopeType.OFFICE,
        scope_id=trip.office_id,
    )
    assert current["office.boarding.open_minutes"]["value"] == 90
