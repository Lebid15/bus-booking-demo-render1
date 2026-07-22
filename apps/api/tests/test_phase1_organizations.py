from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from typing import Any, cast

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from identity.crypto import encrypt_secret
from identity.models import Role, User, UserSession
from organizations.models import (
    Office,
    OfficeDocument,
    OfficeMembership,
    OfficePayoutAccount,
    VerificationCase,
)
from organizations.services import (
    OfficeContext,
    activate_due_payout_accounts,
    approve_payout_account_change,
    assert_office_assignable_for_new_trip,
    command_verification,
    request_payout_account_change,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def make_user(email: str) -> User:
    return User.objects.create_user(full_name=email.split("@")[0], email=email, password="SecurePass!234")


def make_office(*, status: str = Office.Status.DRAFT) -> Office:
    return Office.objects.create(
        legal_name="شركة النقل الوطنية",
        trade_name="النقل الوطنية",
        office_type=Office.OfficeType.CARRIER,
        status=status,
        support_phone="+963900000000",
    )


def make_context(user: User, office: Office, role_code: str) -> OfficeContext:
    role = Role.objects.create(code=role_code, scope_type=Role.ScopeType.OFFICE, name_ar=role_code)
    membership = OfficeMembership.objects.create(user=user, office=office, role=role)
    return OfficeContext(membership=membership, permissions=frozenset())


def request_for(user: User, *, mfa: bool = False):  # type: ignore[no-untyped-def]
    request = RequestFactory().post("/phase1")
    request.user = user
    session = UserSession.objects.create(
        user=user,
        token_hash=hashlib.sha256(f"{user.id}-{mfa}-{uuid.uuid4()}".encode()).digest(),
        expires_at=timezone.now() + timedelta(hours=1),
        mfa_verified_at=timezone.now() if mfa else None,
    )
    cast(Any, request).auth = session
    return request


def add_required_documents(office: Office, *, status: str = OfficeDocument.Status.PENDING) -> None:
    for index, document_type in enumerate(
        ["commercial_registration", "operating_license", "representative_identity"]
    ):
        OfficeDocument.objects.create(
            office=office,
            document_type=document_type,
            storage_object_key=f"private/{document_type}.pdf",
            sha256=f"{index + 1:064x}",
            status=status,
            expires_at=timezone.localdate() + timedelta(days=365),
        )


def assert_code(exc: pytest.ExceptionInfo[DomainAPIException], code: str) -> None:
    assert exc.value.code == code


def test_e02_ac01_incomplete_verification_cannot_be_submitted() -> None:
    owner = make_user("owner-incomplete@example.com")
    office = make_office()
    request = request_for(owner)

    with pytest.raises(DomainAPIException) as exc:
        command_verification(office=office, actor=owner, request=request, command="submit")

    assert_code(exc, "VERIFICATION_INCOMPLETE")
    office.refresh_from_db()
    assert office.status == Office.Status.DRAFT
    assert not VerificationCase.objects.filter(office=office).exists()


def test_e02_ac02_enhanced_verification_requires_distinct_final_approver() -> None:
    reviewer = make_user("reviewer@example.com")
    approver = make_user("approver@example.com")
    office = make_office()
    add_required_documents(office, status=OfficeDocument.Status.VERIFIED)
    case = VerificationCase.objects.create(office=office, risk_level=VerificationCase.RiskLevel.ENHANCED)

    command_verification(office=office, actor=reviewer, request=request_for(reviewer), command="submit")
    command_verification(office=office, actor=reviewer, request=request_for(reviewer), command="start_review")
    with pytest.raises(DomainAPIException) as exc:
        command_verification(office=office, actor=reviewer, request=request_for(reviewer), command="approve")
    assert_code(exc, "DUAL_APPROVAL_REQUIRED")

    approved = command_verification(
        office=office,
        actor=approver,
        request=request_for(approver),
        command="approve",
    )
    assert approved.id == case.id
    assert approved.status == VerificationCase.Status.APPROVED
    assert approved.reviewer_user_id == reviewer.id
    assert approved.approver_user_id == approver.id


def test_e02_ac03_expired_critical_office_document_blocks_new_trip_assignment() -> None:
    office = make_office(status=Office.Status.ACTIVE)
    OfficeDocument.objects.create(
        office=office,
        document_type="operating_license",
        storage_object_key="private/expired.pdf",
        sha256="a" * 64,
        status=OfficeDocument.Status.VERIFIED,
        expires_at=timezone.localdate() - timedelta(days=1),
        is_critical=True,
    )

    with pytest.raises(DomainAPIException) as exc:
        assert_office_assignable_for_new_trip(office)
    assert_code(exc, "VERIFICATION_INCOMPLETE")
    assert exc.value.details == {"reason": "office_critical_document_expired"}


@override_settings(PAYOUT_ACCOUNT_COOLING_HOURS=24, SENSITIVE_MFA_MAX_AGE_SECONDS=900)
def test_e02_ac04_payout_change_requires_mfa_dual_approval_cooling_and_notification() -> None:
    owner = make_user("payout-owner@example.com")
    approver = make_user("payout-approver@example.com")
    office = make_office(status=Office.Status.ACTIVE)
    owner_context = make_context(owner, office, "office.payout.owner")
    approver_context = make_context(approver, office, "office.payout.approver")
    old_account = OfficePayoutAccount.objects.create(
        office=office,
        method_type=OfficePayoutAccount.MethodType.BANK,
        account_holder_name="الحساب القديم",
        account_reference_ciphertext=encrypt_secret("OLD-ACCOUNT-0001"),
        account_reference_last4="0001",
        status=OfficePayoutAccount.Status.ACTIVE,
        created_by=owner,
        approved_by=approver,
        verified_at=timezone.now(),
        effective_at=timezone.now(),
    )
    payload = {
        "method_type": OfficePayoutAccount.MethodType.BANK,
        "account_holder_name": "الحساب الجديد",
        "account_reference": "NEW-ACCOUNT-9999",
    }

    with pytest.raises(DomainAPIException) as no_mfa:
        request_payout_account_change(
            context=owner_context,
            actor=owner,
            request=request_for(owner, mfa=False),
            data=payload,
        )
    assert_code(no_mfa, "AUTH_MFA_REQUIRED")

    account = request_payout_account_change(
        context=owner_context,
        actor=owner,
        request=request_for(owner, mfa=True),
        data=payload,
    )
    with pytest.raises(DomainAPIException) as self_approval:
        approve_payout_account_change(
            context=owner_context,
            actor=owner,
            request=request_for(owner, mfa=True),
            account_id=account.id,
        )
    assert_code(self_approval, "DUAL_APPROVAL_REQUIRED")

    before = timezone.now()
    account = approve_payout_account_change(
        context=approver_context,
        actor=approver,
        request=request_for(approver, mfa=True),
        account_id=account.id,
    )
    assert account.status == OfficePayoutAccount.Status.VERIFIED
    assert account.effective_at is not None
    assert account.effective_at >= before + timedelta(hours=23, minutes=59)
    notification = OutboxEvent.objects.get(
        aggregate_id=account.id,
        event_type="notification.requested",
    )
    assert notification.payload["previous_account_id"] == str(old_account.id)
    assert notification.payload["previous_account_last4"] == "0001"

    assert activate_due_payout_accounts(now=account.effective_at - timedelta(seconds=1)) == 0
    assert activate_due_payout_accounts(now=account.effective_at) == 1
    account.refresh_from_db()
    old_account.refresh_from_db()
    assert account.status == OfficePayoutAccount.Status.ACTIVE
    assert old_account.status == OfficePayoutAccount.Status.REPLACED
