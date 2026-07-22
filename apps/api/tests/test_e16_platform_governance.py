from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from common.exceptions import DomainAPIException
from finance.models import FinancialDispute, FinancialDisputeDecision, LedgerEntry
from finance.services import PostingSpec, assert_entry_balanced, post_ledger_entry
from identity.models import (
    Permission,
    PlatformRoleAssignment,
    Role,
    RolePermission,
    User,
    UserSession,
)
from organizations.models import Office, OfficeMembership
from support.models import OfficeViolation, SupportCase
from trips.public_services import assert_public_bookable

from .test_e13_policies_configuration import _confirmed_booking

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _platform_actor(label: str, permission_codes: list[str], *, mfa: bool = False) -> tuple[User, UserSession | None]:
    user = User.objects.create_user(
        full_name=label,
        email=f"{label.lower().replace(' ', '.')}-{uuid.uuid4().hex[:6]}@example.com",
        is_platform_staff=True,
    )
    role = Role.objects.create(
        code=f"platform.test.{uuid.uuid4().hex}",
        scope_type=Role.ScopeType.PLATFORM,
        name_ar=label,
    )
    for code in permission_codes:
        permission, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name_ar": code, "risk_level": Permission.RiskLevel.CRITICAL},
        )
        RolePermission.objects.create(role=role, permission=permission)
    PlatformRoleAssignment.objects.create(user=user, role=role)
    session = None
    if mfa:
        session = UserSession.objects.create(
            user=user,
            token_hash=f"e16-{uuid.uuid4()}".encode(),
            expires_at=timezone.now() + timedelta(hours=2),
            mfa_verified_at=timezone.now(),
        )
    return user, session


def _grant_office_permission(user: User, office: Office, code: str) -> None:
    membership = OfficeMembership.objects.get(user=user, office=office)
    permission, _ = Permission.objects.get_or_create(
        code=code,
        defaults={"name_ar": code, "risk_level": Permission.RiskLevel.SENSITIVE},
    )
    RolePermission.objects.get_or_create(role=membership.role, permission=permission)


def test_e16_ac01_support_role_cannot_view_or_modify_settlements(api_client: APIClient) -> None:
    support, _ = _platform_actor(
        "Support Agent",
        ["platform.support.manage", "platform.dispute.manage"],
    )
    api_client.force_authenticate(support)

    support_queue = api_client.get("/v1/platform/support-cases")
    settlements = api_client.get("/v1/platform/settlements")
    create_settlement = api_client.post(
        "/v1/platform/settlements",
        {
            "office_id": "missing",
            "period_start": "2026-07-01",
            "period_end": "2026-07-07",
            "currency": "SYP",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-support-settlement-denied",
    )

    assert support_queue.status_code == 200
    assert settlements.status_code == 403
    assert settlements.data["error"]["code"] == "PERMISSION_DENIED"
    assert create_settlement.status_code == 403


@override_settings(SENSITIVE_MFA_MAX_AGE_SECONDS=900)
def test_e16_ac02_critical_suspension_stops_new_sales_and_preserves_existing_booking(api_client: APIClient) -> None:
    booking, _ = _confirmed_booking()
    office = booking.office
    case = SupportCase.objects.create(
        office=office,
        booking=booking,
        trip=booking.trip,
        priority=SupportCase.Priority.P0,
        category="critical_platform_violation",
    )
    OfficeViolation.objects.create(
        office=office,
        support_case=case,
        code="CRITICAL_SAFETY_BREACH",
        severity="P0",
        details={"description": "مخالفة حرجة مثبتة"},
    )
    requester, requester_session = _platform_actor("Compliance Requester", ["platform.office.manage"], mfa=True)
    approver, approver_session = _platform_actor("Independent Approver", ["platform.approval.manage"], mfa=True)
    api_client.force_authenticate(requester, token=requester_session)

    requested = api_client.post(
        f"/v1/platform/offices/{office.public_id}/status",
        {"status": Office.Status.SUSPENDED, "reason": "تعليق بسبب مخالفة سلامة حرجة مثبتة"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-office-suspend-request",
    )

    assert requested.status_code == 200
    assert requested.data["requires_approval"] is True
    office.refresh_from_db()
    assert office.status == Office.Status.ACTIVE

    api_client.force_authenticate(approver, token=approver_session)
    approved = api_client.post(
        f"/v1/platform/approvals/{requested.data['approval']['id']}/commands",
        {"command": "approve", "reason": "مراجعة مستقلة للأدلة واعتماد التعليق"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-office-suspend-approve",
    )

    assert approved.status_code == 200
    assert approved.data["status"] == "executed"
    office.refresh_from_db()
    booking.refresh_from_db()
    assert office.status == Office.Status.SUSPENDED
    assert booking.pk is not None
    assert booking.status != "cancelled"
    with pytest.raises(DomainAPIException) as exc:
        assert_public_bookable(booking.trip)
    assert exc.value.code == "TRIP_NOT_BOOKABLE"


@override_settings(SENSITIVE_MFA_MAX_AGE_SECONDS=900)
def test_e16_ac04_critical_platform_change_requires_mfa_and_second_actor(api_client: APIClient) -> None:
    booking, _ = _confirmed_booking()
    requester, _ = _platform_actor("No MFA Requester", ["platform.office.manage"])
    api_client.force_authenticate(requester)

    rejected = api_client.post(
        f"/v1/platform/offices/{booking.office.public_id}/status",
        {"status": Office.Status.TERMINATED, "reason": "إنهاء حرج يحتاج تحققًا واعتمادًا مزدوجًا"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-no-mfa",
    )
    assert rejected.status_code == 403
    assert rejected.data["error"]["code"] == "AUTH_MFA_REQUIRED"

    session = UserSession.objects.create(
        user=requester,
        token_hash=f"e16-self-{uuid.uuid4()}".encode(),
        expires_at=timezone.now() + timedelta(hours=2),
        mfa_verified_at=timezone.now(),
    )
    api_client.force_authenticate(requester, token=session)
    requested = api_client.post(
        f"/v1/platform/offices/{booking.office.public_id}/status",
        {"status": Office.Status.TERMINATED, "reason": "إنهاء حرج يحتاج تحققًا واعتمادًا مزدوجًا"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-self-request",
    )
    assert requested.status_code == 200

    approval_permission, _ = Permission.objects.get_or_create(
        code="platform.approval.manage",
        defaults={"name_ar": "اعتماد", "risk_level": Permission.RiskLevel.CRITICAL},
    )
    assignment = requester.platform_role_assignments.get()
    RolePermission.objects.create(role=assignment.role, permission=approval_permission)
    self_approval = api_client.post(
        f"/v1/platform/approvals/{requested.data['approval']['id']}/commands",
        {"command": "approve", "reason": "محاولة اعتماد ذاتي يجب منعها"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-self-approve",
    )
    assert self_approval.status_code == 403
    assert self_approval.data["error"]["code"] == "DUAL_APPROVAL_REQUIRED"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e16_ac03_dispute_decision_records_reason_financial_effect_and_one_appeal(api_client: APIClient) -> None:
    booking, _ = _confirmed_booking()
    dispute = FinancialDispute.objects.create(
        booking=booking,
        status=FinancialDispute.Status.UNDER_REVIEW,
        category="service_failure",
        disputed_amount=Decimal("2500.00"),
        currency=booking.currency,
        opened_by_type=FinancialDispute.OpenedByType.CUSTOMER,
    )
    support, _ = _platform_actor("Dispute Support", ["platform.dispute.manage"])
    api_client.force_authenticate(support)
    forbidden = api_client.post(
        f"/v1/platform/disputes/{dispute.id}/commands",
        {
            "command": "decide",
            "decision_code": "OFFICE_CREDIT",
            "reasoning": "الأدلة تثبت مسؤولية المكتب عن الإخفاق التشغيلي.",
            "financial_effect": {"type": "office_credit", "amount": "1000.00"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-dispute-support-forbidden",
    )
    assert forbidden.status_code == 403

    finance_actor, _ = _platform_actor(
        "Dispute Finance",
        ["platform.dispute.manage", "platform.dispute.finance"],
    )
    api_client.force_authenticate(finance_actor)
    decided = api_client.post(
        f"/v1/platform/disputes/{dispute.id}/commands",
        {
            "command": "decide",
            "decision_code": "OFFICE_CREDIT",
            "reasoning": "الأدلة تثبت مسؤولية المكتب ويستحق تعديلًا ماليًا محددًا.",
            "financial_effect": {"type": "office_credit", "amount": "1000.00"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-dispute-decide",
    )
    assert decided.status_code == 200
    assert decided.data["status"] == FinancialDispute.Status.DECIDED
    assert decided.data["initial_decision"]["reasoning"]
    assert decided.data["initial_decision"]["financial_effect"]["amount"] == "1000.00"
    assert decided.data["appeal_deadline_at"] is not None
    initial = FinancialDisputeDecision.objects.get(dispute=dispute, stage="initial")
    assert initial.ledger_entry_id is not None
    assert_entry_balanced(initial.ledger_entry)

    office_actor = booking.trip.created_by
    _grant_office_permission(office_actor, booking.office, "office.support.manage")
    api_client.force_authenticate(office_actor)
    appealed = api_client.post(
        f"/v1/office/disputes/{dispute.id}/appeal",
        {"reason": "يوجد دليل جديد يغير مسؤولية المكتب في الواقعة.", "evidence": {"document": "new-proof"}},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-dispute-appeal",
    )
    assert appealed.status_code == 200
    assert appealed.data["status"] == FinancialDispute.Status.APPEALED

    final_reviewer, _ = _platform_actor(
        "Independent Dispute Reviewer",
        ["platform.dispute.manage", "platform.dispute.finance"],
    )
    api_client.force_authenticate(final_reviewer)
    final = api_client.post(
        f"/v1/platform/disputes/{dispute.id}/commands",
        {
            "command": "decide_appeal",
            "decision_code": "REDUCED_CREDIT",
            "reasoning": "المراجعة المستقلة قبلت الدليل الجديد وخفضت الأثر المالي.",
            "financial_effect": {"type": "office_credit", "amount": "500.00"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="e16-dispute-appeal-decision",
    )
    assert final.status_code == 200
    assert final.data["status"] == FinancialDispute.Status.CLOSED
    assert final.data["appeal_decision"]["is_final"] is True
    assert LedgerEntry.objects.filter(reversal_of=initial.ledger_entry).exists()


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e16_ac05_platform_financial_report_is_derived_from_ledger(api_client: APIClient) -> None:
    booking, _ = _confirmed_booking()
    amount = Decimal("777.00")
    entry = post_ledger_entry(
        event_type="E16_REPORT_PROBE",
        event_id=uuid.uuid4(),
        currency=booking.currency,
        occurred_at=timezone.now(),
        office=booking.office,
        booking=booking,
        description="E16 ledger reporting probe",
        postings=[
            PostingSpec("E16_TEST_ASSET", "asset", "D", amount),
            PostingSpec("E16_TEST_LIABILITY", "liability", "C", amount),
        ],
    )
    assert_entry_balanced(entry)
    reporter, _ = _platform_actor("Platform Reporter", ["platform.report.view"])
    api_client.force_authenticate(reporter)

    response = api_client.get("/v1/platform/reports/summary")

    assert response.status_code == 200
    assert response.data["finance"]["source"] == "ledger_postings"
    currency_row = next(row for row in response.data["finance"]["by_currency"] if row["currency"] == booking.currency)
    expected_debit = sum(
        posting.amount
        for posting in LedgerEntry.objects.filter(currency=booking.currency, occurred_at__date=timezone.localdate())
        for posting in posting.postings.all()
        if posting.direction == "D"
    )
    expected_credit = sum(
        posting.amount
        for posting in LedgerEntry.objects.filter(currency=booking.currency, occurred_at__date=timezone.localdate())
        for posting in posting.postings.all()
        if posting.direction == "C"
    )
    assert Decimal(currency_row["debit"]) == expected_debit
    assert Decimal(currency_row["credit"]) == expected_credit
    assert currency_row["balanced"] is True
