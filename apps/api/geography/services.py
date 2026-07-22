from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpRequest

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from geography.models import Location, Route, RouteStop
from identity.models import User


def _location(public_id: str) -> Location:
    location = Location.objects.filter(public_id=public_id).first()
    if location is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "location_id", "reason": "not_found"}],
        )
    return location


def _validate_parent(location_type: str, parent: Location | None) -> None:
    if location_type == Location.LocationType.CITY:
        if parent is not None:
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": "parent_id", "reason": "city_must_be_root"}],
            )
        return
    if parent is None:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "parent_id", "reason": "required"}],
        )
    if location_type == Location.LocationType.GARAGE and parent.location_type != Location.LocationType.CITY:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "parent_id", "reason": "garage_parent_must_be_city"}],
        )
    if location_type in {
        Location.LocationType.BOARDING_POINT,
        Location.LocationType.DROPOFF_POINT,
    } and parent.location_type not in {
        Location.LocationType.CITY,
        Location.LocationType.GARAGE,
    }:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "parent_id", "reason": "point_parent_must_be_city_or_garage"}],
        )


@transaction.atomic
def create_location(*, actor: User, request: HttpRequest, data: dict[str, Any]) -> Location:
    location_type = data.get("type")
    name_ar = str(data.get("name_ar", "")).strip()
    if not location_type or not name_ar:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "type/name_ar", "reason": "required"}],
        )
    parent_id = data.get("parent_id")
    parent = _location(str(parent_id)) if parent_id else None
    _validate_parent(str(location_type), parent)
    location = Location.objects.create(
        location_type=location_type,
        parent=parent,
        name_ar=name_ar,
        name_en=data.get("name_en") or None,
        address_text=data.get("address") or None,
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        status=data.get("status", Location.Status.ACTIVE),
    )
    record_audit(
        action="platform.location.create",
        object_type="location",
        object_id=location.id,
        actor_user=actor,
        request=request,
        after={"public_id": location.public_id, "type": location.location_type, "name_ar": location.name_ar},
    )
    return location


@transaction.atomic
def update_location(
    *, actor: User, request: HttpRequest, public_id: str, data: dict[str, Any]
) -> Location:
    location = Location.objects.select_for_update().filter(public_id=public_id).first()
    if location is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    before = {
        "type": location.location_type,
        "parent_id": location.parent.public_id if location.parent else None,
        "name_ar": location.name_ar,
        "status": location.status,
    }
    location_type = str(data.get("type", location.location_type))
    if "parent_id" in data:
        parent_id = data.get("parent_id")
        parent = _location(str(parent_id)) if parent_id else None
    else:
        parent = location.parent
    if parent and parent.id == location.id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "parent_id", "reason": "self_reference"}],
        )
    cursor = parent
    while cursor is not None:
        if cursor.id == location.id:
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": "parent_id", "reason": "cycle"}],
            )
        cursor = cursor.parent
    _validate_parent(location_type, parent)
    field_map = {
        "name_ar": "name_ar",
        "name_en": "name_en",
        "address": "address_text",
        "latitude": "latitude",
        "longitude": "longitude",
        "status": "status",
    }
    location.location_type = location_type
    location.parent = parent
    for source, target in field_map.items():
        if source in data:
            value = data[source]
            if source in {"name_en", "address"}:
                value = value or None
            setattr(location, target, value)
    location.full_clean()
    location.save()
    record_audit(
        action="platform.location.update",
        object_type="location",
        object_id=location.id,
        actor_user=actor,
        request=request,
        before=before,
        after={
            "type": location.location_type,
            "parent_id": location.parent.public_id if location.parent else None,
            "name_ar": location.name_ar,
            "status": location.status,
        },
    )
    return location


def _route_endpoint(public_id: str, field: str) -> Location:
    location = _location(public_id)
    if location.status != Location.Status.ACTIVE:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "inactive"}],
        )
    if location.location_type not in {Location.LocationType.CITY, Location.LocationType.GARAGE}:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "endpoint_must_be_city_or_garage"}],
        )
    return location


def _replace_stops(route: Route, stops: Iterable[dict[str, Any]]) -> None:
    prepared: list[RouteStop] = []
    sequences: set[int] = set()
    location_ids: set[uuid.UUID] = set()
    for item in stops:
        sequence = int(item["sequence_no"])
        location = _location(str(item["location_id"]))
        if location.status != Location.Status.ACTIVE:
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": "stops", "reason": "inactive_location"}],
            )
        if sequence in sequences or location.id in location_ids:
            raise DomainAPIException(
                "VALIDATION_ERROR",
                details=[{"field": "stops", "reason": "duplicate_sequence_or_location"}],
            )
        sequences.add(sequence)
        location_ids.add(location.id)
        prepared.append(
            RouteStop(
                route=route,
                sequence_no=sequence,
                location=location,
                stop_type=item["stop_type"],
                offset_minutes=int(item.get("offset_minutes", 0)),
            )
        )
    if sequences and sequences != set(range(1, len(sequences) + 1)):
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "stops", "reason": "sequence_must_be_contiguous"}],
        )
    RouteStop.objects.filter(route=route).delete()
    RouteStop.objects.bulk_create(prepared)


@transaction.atomic
def create_route(*, actor: User, request: HttpRequest, data: dict[str, Any]) -> Route:
    required = [field for field in ("origin_id", "destination_id", "name_ar") if not data.get(field)]
    if required:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": field, "reason": "required"} for field in required],
        )
    origin = _route_endpoint(str(data["origin_id"]), "origin_id")
    destination = _route_endpoint(str(data["destination_id"]), "destination_id")
    if origin.id == destination.id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "destination_id", "reason": "must_differ_from_origin"}],
        )
    try:
        route = Route.objects.create(
            origin_location=origin,
            destination_location=destination,
            name_ar=str(data["name_ar"]).strip(),
            status=data.get("status", Route.Status.ACTIVE),
        )
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "route_direction_exists"}) from exc
    _replace_stops(route, data.get("stops", []))
    record_audit(
        action="platform.route.create",
        object_type="route",
        object_id=route.id,
        actor_user=actor,
        request=request,
        after={"origin_id": origin.public_id, "destination_id": destination.public_id, "name_ar": route.name_ar},
    )
    return route


@transaction.atomic
def update_route(*, actor: User, request: HttpRequest, public_id: str, data: dict[str, Any]) -> Route:
    route = (
        Route.objects.select_for_update()
        .select_related("origin_location", "destination_location")
        .filter(public_id=public_id)
        .first()
    )
    if route is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    before = {
        "origin_id": route.origin_location.public_id,
        "destination_id": route.destination_location.public_id,
        "name_ar": route.name_ar,
        "status": route.status,
    }
    origin = (
        _route_endpoint(str(data["origin_id"]), "origin_id")
        if "origin_id" in data
        else route.origin_location
    )
    destination = (
        _route_endpoint(str(data["destination_id"]), "destination_id")
        if "destination_id" in data
        else route.destination_location
    )
    if origin.id == destination.id:
        raise DomainAPIException(
            "VALIDATION_ERROR",
            details=[{"field": "destination_id", "reason": "must_differ_from_origin"}],
        )
    route.origin_location = origin
    route.destination_location = destination
    if "name_ar" in data:
        route.name_ar = str(data["name_ar"]).strip()
    if "status" in data:
        route.status = str(data["status"])
    try:
        route.full_clean()
        route.save()
    except IntegrityError as exc:
        raise DomainAPIException("CONFLICT", details={"reason": "route_direction_exists"}) from exc
    if "stops" in data:
        _replace_stops(route, data["stops"])
    record_audit(
        action="platform.route.update",
        object_type="route",
        object_id=route.id,
        actor_user=actor,
        request=request,
        before=before,
        after={
            "origin_id": route.origin_location.public_id,
            "destination_id": route.destination_location.public_id,
            "name_ar": route.name_ar,
            "status": route.status,
        },
    )
    return route
