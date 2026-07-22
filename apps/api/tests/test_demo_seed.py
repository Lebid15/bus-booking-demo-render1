from __future__ import annotations

from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from identity.models import User
from organizations.models import Office
from trips.models import Trip


@override_settings(APP_ENV="local", DEMO_MODE=True, SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_demo_seed_is_idempotent_and_accounts_can_login(db) -> None:  # type: ignore[no-untyped-def]
    call_command("seed_demo", verbosity=0)
    first_trip_ids = set(Trip.objects.filter(status=Trip.Status.BOOKING_OPEN).values_list("id", flat=True))
    call_command("seed_demo", verbosity=0)

    assert User.objects.filter(email="admin@demo.local", is_platform_staff=True).count() == 1
    assert User.objects.filter(email="office@demo.local", is_platform_staff=False).count() == 1
    assert Office.objects.filter(support_email="office@demo.local", status=Office.Status.ACTIVE).count() == 1
    assert len(first_trip_ids) == 8
    assert set(Trip.objects.filter(status=Trip.Status.BOOKING_OPEN).values_list("id", flat=True)) == first_trip_ids

    client = APIClient()
    response = client.post(
        "/v1/auth/login",
        {"identifier": "office@demo.local", "password": "DemoOffice!2026"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["landing_path"] == "/office"
    assert response.data["user"]["office"]["name"] == "مكتب بولمن الشام"
