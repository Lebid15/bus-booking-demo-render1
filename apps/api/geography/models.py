from __future__ import annotations

from django.db import models
from django.db.models import F, Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel


class Location(UUIDPrimaryKeyModel):
    class LocationType(models.TextChoices):
        CITY = "city", "City"
        GARAGE = "garage", "Garage"
        BOARDING_POINT = "boarding_point", "Boarding point"
        DROPOFF_POINT = "dropoff_point", "Drop-off point"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    location_type = models.CharField(max_length=20, choices=LocationType.choices)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="children",
    )
    name_ar = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160, null=True, blank=True)
    address_text = models.TextField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "locations"
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="ck_location_latitude",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="ck_location_longitude",
            ),
        ]
        indexes = [
            models.Index(fields=["location_type", "status"], name="ix_location_type_status"),
            models.Index(fields=["parent", "status"], name="ix_location_parent_status"),
        ]
        ordering = ["name_ar", "public_id"]


class Route(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    origin_location = models.ForeignKey(
        Location,
        on_delete=models.RESTRICT,
        related_name="origin_routes",
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.RESTRICT,
        related_name="destination_routes",
    )
    name_ar = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "routes"
        constraints = [
            models.CheckConstraint(
                condition=~Q(origin_location=F("destination_location")),
                name="ck_route_distinct_endpoints",
            ),
            models.UniqueConstraint(
                fields=["origin_location", "destination_location"],
                name="uq_route_direction",
            ),
        ]
        indexes = [models.Index(fields=["status", "created_at"], name="ix_route_status_created")]
        ordering = ["name_ar", "public_id"]


class RouteStop(models.Model):
    class StopType(models.TextChoices):
        BOARDING = "boarding", "Boarding"
        DROPOFF = "dropoff", "Drop-off"
        BOTH = "both", "Both"

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    sequence_no = models.PositiveSmallIntegerField()
    location = models.ForeignKey(Location, on_delete=models.RESTRICT, related_name="route_stops")
    stop_type = models.CharField(max_length=20, choices=StopType.choices)
    offset_minutes = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "route_stops"
        constraints = [
            models.CheckConstraint(condition=Q(sequence_no__gt=0), name="ck_route_stop_sequence"),
            models.UniqueConstraint(fields=["route", "sequence_no"], name="pk_route_stops"),
            models.UniqueConstraint(fields=["route", "location"], name="uq_route_stop_location"),
        ]
        ordering = ["sequence_no"]
