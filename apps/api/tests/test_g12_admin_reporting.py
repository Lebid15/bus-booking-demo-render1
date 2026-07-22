from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from adminops.models import OfficeStatusAction
from identity.models import Permission, Role, RolePermission, User
from organizations.models import Office, OfficeMembership
from support.models import OfficeViolation, SupportCase

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _user(label: str, *, platform: bool = False) -> User:
    return User.objects.create_user(
        full_name=label,
        email=f"{label.lower().replace(' ', '.')}-{uuid.uuid4().hex[:6]}@example.com",
        is_platform_staff=platform,
    )


def _office(label: str, status: str = Office.Status.ACTIVE) -> Office:
    return Office.objects.create(
        legal_name=f"{label} Legal",
        trade_name=label,
        office_type=Office.OfficeType.CARRIER,
        status=status,
        support_phone="+963900000000",
    )


def _office_report_user(office: Office) -> User:
    user = _user("Office Reporter")
    permission = Permission.objects.create(
        code="office.report.view",
        name_ar="عرض تقارير المكتب",
        risk_level=Permission.RiskLevel.SENSITIVE,
    )
    role = Role.objects.create(
        code=f"office.reporter.{uuid.uuid4().hex[:8]}",
        scope_type=Role.ScopeType.OFFICE,
        name_ar="مراجع تقارير",
    )
    RolePermission.objects.create(role=role, permission=permission)
    OfficeMembership.objects.create(user=user, office=office, role=role)
    return user


def test_g12_platform_office_search_and_idempotent_status_change(api_client: APIClient) -> None:
    actor = _user("Platform Operator", platform=True)
    office = _office("شركة الفرات", status=Office.Status.RESTRICTED)
    api_client.force_authenticate(actor)

    search = api_client.get("/v1/platform/offices", {"q": "الفرات"})
    assert search.status_code == 200
    assert [row["id"] for row in search.data] == [office.public_id]

    payload = {"status": Office.Status.NO_NEW_BOOKINGS, "reason": "مخالفة تشغيلية حرجة مثبتة"}
    first = api_client.post(
        f"/v1/platform/offices/{office.public_id}/status",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="g12-office-status-001",
    )
    replay = api_client.post(
        f"/v1/platform/offices/{office.public_id}/status",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="g12-office-status-001",
    )

    assert first.status_code == replay.status_code == 200
    assert first.data == replay.data
    assert OfficeStatusAction.objects.filter(office=office).count() == 1
    office.refresh_from_db()
    assert office.status == Office.Status.NO_NEW_BOOKINGS


def test_g12_violation_uses_support_domain_and_is_idempotent(api_client: APIClient) -> None:
    actor = _user("Compliance Officer", platform=True)
    office = _office("شركة البادية")
    api_client.force_authenticate(actor)
    payload = {
        "code": "CRITICAL_OPERATIONAL_BREACH",
        "severity": "P1",
        "description": "تكرار مخالفة تشغيلية موثقة تتطلب متابعة مباشرة.",
        "evidence": {"case_ref": "OPS-77"},
    }

    first = api_client.post(
        f"/v1/platform/offices/{office.public_id}/violations",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="g12-violation-001",
    )
    replay = api_client.post(
        f"/v1/platform/offices/{office.public_id}/violations",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="g12-violation-001",
    )

    assert first.status_code == replay.status_code == 200
    assert first.data == replay.data
    assert OfficeViolation.objects.filter(office=office).count() == 1
    assert SupportCase.objects.filter(office=office, category="platform_violation").count() == 1

    violation_id = first.data["id"]
    closed = api_client.post(
        f"/v1/platform/offices/{office.public_id}/violations/{violation_id}/commands",
        {"command": "close", "reason": "تمت معالجة المخالفة والتحقق من الإجراء التصحيحي."},
        format="json",
        HTTP_IDEMPOTENCY_KEY="g12-violation-close-001",
    )
    assert closed.status_code == 200
    assert closed.data["status"] == OfficeViolation.Status.CLOSED
    assert SupportCase.objects.get(office=office).status == SupportCase.Status.CLOSED


def test_g12_office_report_ignores_foreign_office_query_parameter(api_client: APIClient) -> None:
    office_a = _office("مكتب ألف")
    office_b = _office("مكتب باء")
    user = _office_report_user(office_a)
    case = SupportCase.objects.create(
        office=office_b,
        opened_by_user=user,
        priority=SupportCase.Priority.P1,
        category="platform_violation",
    )
    OfficeViolation.objects.create(
        office=office_b,
        support_case=case,
        code="OFFICE_B_ONLY",
        severity="P1",
    )
    api_client.force_authenticate(user)

    response = api_client.get("/v1/office/reports/summary", {"office_id": office_b.public_id})

    assert response.status_code == 200
    assert response.data["open_violations"] == 0
