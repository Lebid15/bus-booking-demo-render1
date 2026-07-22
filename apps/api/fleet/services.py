from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from fleet.models import (
    Driver,
    SeatAdjacency,
    SeatLayout,
    SeatLayoutSeat,
    Vehicle,
    VehicleDocument,
)
from identity.crypto import encrypt_secret
from identity.models import User
from organizations.services import OfficeContext


def _layout_for_office(*, office_id: uuid.UUID, layout_id: str, lock: bool = False) -> SeatLayout:
    queryset = SeatLayout.objects.filter(id=layout_id, office_id=office_id)
    if lock:
        queryset = queryset.select_for_update()
    layout = queryset.first()
    if layout is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return layout


def _validate_layout_payload(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seats = list(data.get("seats", []))
    adjacencies = list(data.get("adjacencies", []))
    if not seats:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "seats", "reason": "at_least_one_required"}],
        )
    codes: set[str] = set()
    positions: set[tuple[int, int]] = set()
    for seat in seats:
        code = str(seat["code"]).strip().upper()
        position = (int(seat["row"]), int(seat["column"]))
        if code in codes:
            raise DomainAPIException(
                "SEAT_LAYOUT_MISMATCH",
                details={"reason": "duplicate_seat_code", "seat": code},
            )
        if position in positions:
            raise DomainAPIException(
                "SEAT_LAYOUT_MISMATCH",
                details={"reason": "duplicate_position", "position": position},
            )
        codes.add(code)
        positions.add(position)
        seat["code"] = code
    pairs: set[tuple[str, str]] = set()
    for adjacency in adjacencies:
        seat_a = str(adjacency["seat_a"]).strip().upper()
        seat_b = str(adjacency["seat_b"]).strip().upper()
        if seat_a == seat_b or seat_a not in codes or seat_b not in codes:
            raise DomainAPIException(
                "SEAT_LAYOUT_MISMATCH",
                details={"reason": "invalid_adjacency", "seat_a": seat_a, "seat_b": seat_b},
            )
        pair: tuple[str, str] = (seat_a, seat_b) if seat_a < seat_b else (seat_b, seat_a)
        if pair in pairs:
            raise DomainAPIException(
                "SEAT_LAYOUT_MISMATCH",
                details={"reason": "duplicate_adjacency", "seat_a": pair[0], "seat_b": pair[1]},
            )
        pairs.add(pair)
        adjacency["seat_a"], adjacency["seat_b"] = pair
    return seats, adjacencies


def _write_layout_children(
    layout: SeatLayout,
    seats: list[dict[str, Any]],
    adjacencies: list[dict[str, Any]],
) -> None:
    created_seats = SeatLayoutSeat.objects.bulk_create(
        [
            SeatLayoutSeat(
                layout=layout,
                seat_code=seat["code"],
                row_no=seat["row"],
                column_no=seat["column"],
                seat_type=seat.get("type", SeatLayoutSeat.SeatType.STANDARD),
                is_sellable=seat.get("sellable", True),
                metadata=seat.get("metadata", {}),
            )
            for seat in seats
        ]
    )
    by_code = {seat.seat_code: seat for seat in created_seats}
    adjacency_rows: list[SeatAdjacency] = []
    for adjacency in adjacencies:
        seat_a = by_code[adjacency["seat_a"]]
        seat_b = by_code[adjacency["seat_b"]]
        if str(seat_a.id) > str(seat_b.id):
            seat_a, seat_b = seat_b, seat_a
        adjacency_rows.append(
            SeatAdjacency(
                layout=layout,
                seat_a=seat_a,
                seat_b=seat_b,
                adjacency_type=adjacency.get("type", SeatAdjacency.AdjacencyType.SAME_UNIT),
            )
        )
    SeatAdjacency.objects.bulk_create(adjacency_rows)


@transaction.atomic
def create_seat_layout(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> SeatLayout:
    seats, adjacencies = _validate_layout_payload(data)
    try:
        layout = SeatLayout.objects.create(
            office=context.office,
            name=str(data["name"]).strip(),
            layout_type=data["layout_type"],
            seat_count=len(seats),
            version=1,
            status=data.get("status", SeatLayout.Status.ACTIVE),
        )
        _write_layout_children(layout, seats, adjacencies)
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "layout_name_version_exists"}) from exc
    record_audit(
        action="office.seat_layout.create",
        object_type="seat_layout",
        object_id=layout.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"name": layout.name, "version": layout.version, "seat_count": layout.seat_count},
    )
    return layout


@transaction.atomic
def version_seat_layout(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    layout_id: str,
    data: dict[str, Any],
) -> SeatLayout:
    base = _layout_for_office(office_id=context.office.id, layout_id=layout_id, lock=True)
    seats, adjacencies = _validate_layout_payload(data)
    latest = (
        SeatLayout.objects.select_for_update()
        .filter(office=context.office, name=base.name)
        .aggregate(max_version=Max("version"))["max_version"]
        or 0
    )
    new_layout = SeatLayout.objects.create(
        office=context.office,
        name=str(data.get("name", base.name)).strip(),
        layout_type=data.get("layout_type", base.layout_type),
        seat_count=len(seats),
        version=latest + 1,
        status=data.get("status", SeatLayout.Status.ACTIVE),
    )
    _write_layout_children(new_layout, seats, adjacencies)
    if base.status == SeatLayout.Status.ACTIVE:
        base.status = SeatLayout.Status.RETIRED
        base.save(update_fields=["status"])
    record_audit(
        action="office.seat_layout.version",
        object_type="seat_layout",
        object_id=new_layout.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before={"layout_id": str(base.id), "version": base.version, "status": base.status},
        after={"layout_id": str(new_layout.id), "version": new_layout.version, "seat_count": new_layout.seat_count},
    )
    return new_layout


@transaction.atomic
def create_vehicle(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> Vehicle:
    from subscriptions.services import require_usage_capacity

    require_usage_capacity(context.office, "vehicles")
    required = [field for field in ("plate_number", "seat_layout_id") if not data.get(field)]
    if required:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "required"} for field in required],
        )
    layout = _layout_for_office(
        office_id=context.office.id,
        layout_id=str(data["seat_layout_id"]),
    )
    if layout.status != SeatLayout.Status.ACTIVE:
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "seat_layout_not_active"})
    try:
        vehicle = Vehicle.objects.create(
            office=context.office,
            operator=context.office.operator,
            plate_number=str(data["plate_number"]).strip().upper(),
            fleet_number=data.get("fleet_number") or None,
            seat_layout=layout,
            status=data.get("status", Vehicle.Status.ACTIVE),
            make_model=data.get("make_model") or None,
            year=data.get("year"),
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "plate_number_exists"}) from exc
    record_audit(
        action="office.vehicle.create",
        object_type="vehicle",
        object_id=vehicle.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"public_id": vehicle.public_id, "plate_number": vehicle.plate_number, "layout_id": str(layout.id)},
    )
    return vehicle


@transaction.atomic
def update_vehicle(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    vehicle_id: str,
    data: dict[str, Any],
) -> Vehicle:
    vehicle = (
        Vehicle.objects.select_for_update()
        .select_related("seat_layout")
        .filter(public_id=vehicle_id, office=context.office)
        .first()
    )
    if vehicle is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    before = {
        "seat_layout_id": str(vehicle.seat_layout_id),
        "status": vehicle.status,
        "make_model": vehicle.make_model,
        "year": vehicle.year,
    }
    if vehicle.status == Vehicle.Status.RETIRED and data.get("status") not in {None, Vehicle.Status.RETIRED}:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED", details={"reason": "retired_vehicle_is_terminal"})
    if "seat_layout_id" in data:
        layout = _layout_for_office(
            office_id=context.office.id,
            layout_id=str(data["seat_layout_id"]),
        )
        if layout.status != SeatLayout.Status.ACTIVE:
            raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "seat_layout_not_active"})
        vehicle.seat_layout = layout
    for field in ("status", "make_model", "year", "fleet_number"):
        if field in data:
            value = data[field]
            if field in {"make_model", "fleet_number"}:
                value = value or None
            setattr(vehicle, field, value)
    vehicle.full_clean()
    vehicle.save()
    record_audit(
        action="office.vehicle.update",
        object_type="vehicle",
        object_id=vehicle.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before=before,
        after={
            "seat_layout_id": str(vehicle.seat_layout_id),
            "status": vehicle.status,
            "make_model": vehicle.make_model,
            "year": vehicle.year,
        },
    )
    return vehicle


@transaction.atomic
def create_driver(
    *, context: OfficeContext, actor: User, request: HttpRequest, data: dict[str, Any]
) -> Driver:
    if context.office.operator_id is None:
        raise DomainAPIException(
            "VERIFICATION_INCOMPLETE",
            details={"reason": "office_operator_required_for_driver"},
        )
    required = [field for field in ("full_name", "license_number") if not data.get(field)]
    if required:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "required"} for field in required],
        )
    license_number = str(data["license_number"]).strip()
    driver = Driver.objects.create(
        operator=context.office.operator,
        full_name=str(data["full_name"]).strip(),
        phone=data.get("phone") or None,
        license_number_ciphertext=encrypt_secret(license_number),
        license_last4=license_number[-4:],
        license_expires_at=data.get("license_expires_at"),
        status=data.get("status", Driver.Status.ACTIVE),
    )
    record_audit(
        action="office.driver.create",
        object_type="driver",
        object_id=driver.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"public_id": driver.public_id, "full_name": driver.full_name, "license_last4": driver.license_last4},
    )
    return driver


@transaction.atomic
def update_driver(
    *,
    context: OfficeContext,
    actor: User,
    request: HttpRequest,
    driver_id: str,
    data: dict[str, Any],
) -> Driver:
    if context.office.operator_id is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    driver = Driver.objects.select_for_update().filter(
        public_id=driver_id,
        operator_id=context.office.operator_id,
    ).first()
    if driver is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    before = {
        "phone": driver.phone,
        "license_expires_at": driver.license_expires_at.isoformat() if driver.license_expires_at else None,
        "status": driver.status,
    }
    for field in ("full_name", "phone", "license_expires_at", "status"):
        if field in data:
            value = data[field]
            if field == "phone":
                value = value or None
            setattr(driver, field, value)
    if "license_number" in data and data["license_number"]:
        license_number = str(data["license_number"]).strip()
        driver.license_number_ciphertext = encrypt_secret(license_number)
        driver.license_last4 = license_number[-4:]
    if (
        driver.status == Driver.Status.ACTIVE
        and driver.license_expires_at is not None
        and driver.license_expires_at < timezone.localdate()
    ):
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "driver_license_expired"})
    driver.save()
    record_audit(
        action="office.driver.update",
        object_type="driver",
        object_id=driver.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before=before,
        after={
            "phone": driver.phone,
            "license_expires_at": driver.license_expires_at.isoformat() if driver.license_expires_at else None,
            "status": driver.status,
        },
    )
    return driver


def assert_vehicle_assignable(vehicle: Vehicle, *, service_date: date | None = None) -> None:
    on_date = service_date or timezone.localdate()
    if vehicle.status != Vehicle.Status.ACTIVE:
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "vehicle_not_active"})
    invalid_document = vehicle.documents.filter(is_critical=True).filter(
        ~Q(status=VehicleDocument.Status.VERIFIED) | Q(expires_at__lt=on_date)
    ).first()
    if invalid_document is not None:
        raise DomainAPIException(
            "VERIFICATION_INCOMPLETE",
            details={"reason": "vehicle_document_invalid", "document_type": invalid_document.document_type},
        )


def assert_driver_assignable(driver: Driver, *, service_date: date | None = None) -> None:
    on_date = service_date or timezone.localdate()
    if driver.status != Driver.Status.ACTIVE:
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "driver_not_active"})
    if driver.license_expires_at is None or driver.license_expires_at < on_date:
        raise DomainAPIException("VERIFICATION_INCOMPLETE", details={"reason": "driver_license_invalid"})
