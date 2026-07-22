from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from common.exceptions import DomainAPIException
from fleet.models import Driver, SeatAdjacency, SeatLayout, Vehicle, VehicleDocument
from fleet.services import (
    assert_driver_assignable,
    assert_vehicle_assignable,
    create_seat_layout,
    version_seat_layout,
)
from geography.models import Location, Route
from geography.services import create_route
from identity.models import Role, User
from organizations.models import Office, OfficeMembership, TransportOperator
from organizations.services import OfficeContext

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def actor_and_context() -> tuple[User, OfficeContext]:
    user = User.objects.create_user(
        full_name="مدير الأسطول",
        email="fleet@example.com",
        password="SecurePass!234",
    )
    operator = TransportOperator.objects.create(legal_name="الناقل الوطني", status="active")
    office = Office.objects.create(
        operator=operator,
        legal_name="مكتب الناقل",
        trade_name="الناقل",
        office_type=Office.OfficeType.CARRIER,
        status=Office.Status.ACTIVE,
        support_phone="+963900000000",
    )
    role = Role.objects.create(code="office.fleet.owner", scope_type=Role.ScopeType.OFFICE, name_ar="أسطول")
    membership = OfficeMembership.objects.create(user=user, office=office, role=role)
    return user, OfficeContext(membership=membership, permissions=frozenset())


def request_for(user: User):  # type: ignore[no-untyped-def]
    request = RequestFactory().post("/phase1")
    request.user = user
    return request


def layout_payload() -> dict[str, object]:
    return {
        "name": "بولمان 2+2",
        "layout_type": SeatLayout.LayoutType.TWO_PLUS_TWO,
        "seats": [
            {"code": "1A", "row": 1, "column": 1},
            {"code": "1B", "row": 1, "column": 2},
            {"code": "1C", "row": 1, "column": 4},
            {"code": "1D", "row": 1, "column": 5},
        ],
        "adjacencies": [
            {"seat_a": "1A", "seat_b": "1B", "type": SeatAdjacency.AdjacencyType.SAME_UNIT},
            {"seat_a": "1B", "seat_b": "1C", "type": SeatAdjacency.AdjacencyType.AISLE},
            {"seat_a": "1C", "seat_b": "1D", "type": SeatAdjacency.AdjacencyType.SAME_UNIT},
        ],
    }


def test_e03_ac01_reverse_direction_is_not_inferred() -> None:
    actor, _ = actor_and_context()
    raqqa = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="الرقة")
    damascus = Location.objects.create(location_type=Location.LocationType.CITY, name_ar="دمشق")

    route = create_route(
        actor=actor,
        request=request_for(actor),
        data={
            "origin_id": raqqa.public_id,
            "destination_id": damascus.public_id,
            "name_ar": "الرقة - دمشق",
        },
    )

    assert route.origin_location == raqqa
    assert not Route.objects.filter(origin_location=damascus, destination_location=raqqa).exists()


def test_e03_ac02_duplicate_seat_position_is_rejected() -> None:
    actor, context = actor_and_context()
    payload = layout_payload()
    payload["seats"] = [
        {"code": "1A", "row": 1, "column": 1},
        {"code": "1B", "row": 1, "column": 1},
    ]
    payload["adjacencies"] = []

    with pytest.raises(DomainAPIException) as exc:
        create_seat_layout(context=context, actor=actor, request=request_for(actor), data=payload)
    assert exc.value.code == "SEAT_LAYOUT_MISMATCH"
    assert isinstance(exc.value.details, dict)
    assert exc.value.details["reason"] == "duplicate_position"


def test_e03_ac03_across_aisle_is_not_same_unit() -> None:
    actor, context = actor_and_context()
    layout = create_seat_layout(
        context=context,
        actor=actor,
        request=request_for(actor),
        data=layout_payload(),
    )

    adjacency = layout.adjacencies.get(adjacency_type=SeatAdjacency.AdjacencyType.AISLE)
    assert {adjacency.seat_a.seat_code, adjacency.seat_b.seat_code} == {"1B", "1C"}
    assert not layout.adjacencies.filter(
        adjacency_type=SeatAdjacency.AdjacencyType.SAME_UNIT,
        seat_a__seat_code__in=["1B", "1C"],
        seat_b__seat_code__in=["1B", "1C"],
    ).exists()


def test_e03_ac04_inactive_or_expired_resources_are_not_assignable() -> None:
    actor, context = actor_and_context()
    layout = create_seat_layout(
        context=context,
        actor=actor,
        request=request_for(actor),
        data=layout_payload(),
    )
    vehicle = Vehicle.objects.create(
        office=context.office,
        operator=context.office.operator,
        plate_number="RAQ-100",
        seat_layout=layout,
        status=Vehicle.Status.OUT_OF_SERVICE,
    )
    with pytest.raises(DomainAPIException) as inactive:
        assert_vehicle_assignable(vehicle)
    assert inactive.value.details == {"reason": "vehicle_not_active"}

    vehicle.status = Vehicle.Status.ACTIVE
    vehicle.save(update_fields=["status"])
    VehicleDocument.objects.create(
        vehicle=vehicle,
        document_type="technical_inspection",
        storage_object_key="private/vehicle.pdf",
        sha256="b" * 64,
        status=VehicleDocument.Status.VERIFIED,
        expires_at=timezone.localdate() - timedelta(days=1),
    )
    with pytest.raises(DomainAPIException) as expired_document:
        assert_vehicle_assignable(vehicle)
    assert isinstance(expired_document.value.details, dict)
    assert expired_document.value.details["reason"] == "vehicle_document_invalid"

    driver = Driver.objects.create(
        operator=context.office.operator,
        full_name="سائق تجريبي",
        license_number_ciphertext=b"encrypted",
        license_expires_at=timezone.localdate() - timedelta(days=1),
        status=Driver.Status.ACTIVE,
    )
    with pytest.raises(DomainAPIException) as expired_license:
        assert_driver_assignable(driver)
    assert expired_license.value.details == {"reason": "driver_license_invalid"}


def test_e03_ac05_layout_change_creates_version_and_keeps_existing_vehicle_snapshot_reference() -> None:
    actor, context = actor_and_context()
    first = create_seat_layout(
        context=context,
        actor=actor,
        request=request_for(actor),
        data=layout_payload(),
    )
    vehicle = Vehicle.objects.create(
        office=context.office,
        operator=context.office.operator,
        plate_number="RAQ-200",
        seat_layout=first,
    )
    changed = layout_payload()
    existing_seats = changed["seats"]
    assert isinstance(existing_seats, list)
    changed["seats"] = [*existing_seats, {"code": "2A", "row": 2, "column": 1}]
    second = version_seat_layout(
        context=context,
        actor=actor,
        request=request_for(actor),
        layout_id=str(first.id),
        data=changed,
    )

    first.refresh_from_db()
    vehicle.refresh_from_db()
    assert first.status == SeatLayout.Status.RETIRED
    assert second.version == 2
    assert second.id != first.id
    assert vehicle.seat_layout_id == first.id
