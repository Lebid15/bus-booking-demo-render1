from __future__ import annotations

import pytest

from identity.models import Permission, Role, RolePermission, User
from organizations.models import Office, OfficeMembership

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.security]


def login(client, user: User) -> str:  # type: ignore[no-untyped-def]
    response = client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    )
    return str(response.data["access_token"])


def office(name: str) -> Office:
    return Office.objects.create(
        legal_name=name,
        trade_name=name,
        office_type=Office.OfficeType.GARAGE_OFFICE,
        status=Office.Status.ACTIVE,
        support_phone="+963900000000",
    )


def test_office_context_is_derived_from_membership_not_request_office_id(api_client):  # type: ignore[no-untyped-def]
    user = User.objects.create_user(
        full_name="موظف مكتب",
        email="clerk@example.com",
        password="SecurePass!234",
    )
    permission = Permission.objects.create(
        code="office.booking.create", name_ar="إنشاء حجز", risk_level="normal"
    )
    role = Role.objects.create(code="office.booking_agent", scope_type="office", name_ar="موظف حجوزات")
    RolePermission.objects.create(role=role, permission=permission)
    own_office = office("مكتب الرقة")
    other_office = office("مكتب دمشق")
    OfficeMembership.objects.create(user=user, office=own_office, role=role)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login(api_client, user)}")
    response = api_client.get(
        "/v1/office/context",
        HTTP_X_OFFICE_ID=str(other_office.id),
    )
    assert response.status_code == 200
    assert response.data["office"]["public_id"] == own_office.public_id
    assert response.data["permissions"] == ["office.booking.create"]


def test_ambiguous_membership_context_fails_closed(api_client):  # type: ignore[no-untyped-def]
    user = User.objects.create_user(
        full_name="موظف متعدد",
        email="multi@example.com",
        password="SecurePass!234",
    )
    role = Role.objects.create(code="office.booking_agent", scope_type="office", name_ar="موظف حجوزات")
    OfficeMembership.objects.create(user=user, office=office("A"), role=role)
    OfficeMembership.objects.create(user=user, office=office("B"), role=role)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login(api_client, user)}")
    response = api_client.get("/v1/office/context")
    assert response.status_code == 403
    assert response.data["error"]["code"] == "TENANT_ACCESS_DENIED"
