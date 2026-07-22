from __future__ import annotations

from django.db import models
from django.db.models import F, Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel
from organizations.models import Office, TransportOperator


class SeatLayout(UUIDPrimaryKeyModel):
    class LayoutType(models.TextChoices):
        TWO_PLUS_TWO = "2+2", "2+2"
        TWO_PLUS_ONE = "2+1", "2+1"
        CUSTOM = "custom", "Custom"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="seat_layouts")
    name = models.CharField(max_length=160)
    layout_type = models.CharField(max_length=20, choices=LayoutType.choices)
    seat_count = models.PositiveSmallIntegerField()
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "seat_layouts"
        constraints = [
            models.CheckConstraint(condition=Q(seat_count__gt=0), name="ck_seat_layout_count"),
            models.UniqueConstraint(
                fields=["office", "name", "version"],
                name="uq_seat_layout_version",
            ),
        ]
        indexes = [models.Index(fields=["office", "status"], name="ix_layout_office_status")]
        ordering = ["name", "-version"]


class SeatLayoutSeat(UUIDPrimaryKeyModel):
    class SeatType(models.TextChoices):
        STANDARD = "standard", "Standard"
        VIP = "vip", "VIP"
        SINGLE = "single", "Single"
        ACCESSIBLE = "accessible", "Accessible"
        CREW = "crew", "Crew"
        BLOCKED = "blocked", "Blocked"

    layout = models.ForeignKey(SeatLayout, on_delete=models.CASCADE, related_name="seats")
    seat_code = models.CharField(max_length=12)
    row_no = models.PositiveSmallIntegerField()
    column_no = models.PositiveSmallIntegerField()
    seat_type = models.CharField(max_length=20, choices=SeatType.choices, default=SeatType.STANDARD)
    is_sellable = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "seat_layout_seats"
        constraints = [
            models.CheckConstraint(condition=Q(row_no__gt=0, column_no__gt=0), name="ck_layout_seat_position"),
            models.UniqueConstraint(fields=["layout", "seat_code"], name="uq_layout_seat_code"),
            models.UniqueConstraint(
                fields=["layout", "row_no", "column_no"],
                name="uq_layout_seat_position",
            ),
        ]
        ordering = ["row_no", "column_no", "seat_code"]


class SeatAdjacency(models.Model):
    class AdjacencyType(models.TextChoices):
        SAME_UNIT = "same_unit", "Same unit"
        AISLE = "aisle", "Across aisle"
        NEARBY = "nearby", "Nearby"

    layout = models.ForeignKey(SeatLayout, on_delete=models.CASCADE, related_name="adjacencies")
    seat_a = models.ForeignKey(SeatLayoutSeat, on_delete=models.CASCADE, related_name="adjacent_as_a")
    seat_b = models.ForeignKey(SeatLayoutSeat, on_delete=models.CASCADE, related_name="adjacent_as_b")
    adjacency_type = models.CharField(
        max_length=20,
        choices=AdjacencyType.choices,
        default=AdjacencyType.SAME_UNIT,
    )

    class Meta:
        db_table = "seat_adjacencies"
        constraints = [
            models.CheckConstraint(condition=Q(seat_a_id__lt=F("seat_b_id")), name="ck_seat_adjacency_order"),
            models.UniqueConstraint(
                fields=["layout", "seat_a", "seat_b"],
                name="pk_seat_adjacencies",
            ),
        ]


class Vehicle(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MAINTENANCE = "maintenance", "Maintenance"
        OUT_OF_SERVICE = "out_of_service", "Out of service"
        RETIRED = "retired", "Retired"

    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="vehicles")
    operator = models.ForeignKey(
        TransportOperator,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="vehicles",
    )
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    plate_number = models.CharField(max_length=40)
    fleet_number = models.CharField(max_length=40, null=True, blank=True)
    seat_layout = models.ForeignKey(SeatLayout, on_delete=models.RESTRICT, related_name="vehicles")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    make_model = models.CharField(max_length=160, null=True, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vehicles"
        constraints = [
            models.UniqueConstraint(fields=["office", "plate_number"], name="uq_vehicle_plate_office"),
            models.CheckConstraint(
                condition=Q(year__isnull=True) | Q(year__gte=1980, year__lte=2100),
                name="ck_vehicle_year",
            ),
        ]
        indexes = [models.Index(fields=["office", "status"], name="ix_vehicle_office_status")]
        ordering = ["plate_number"]


class VehicleDocument(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.RESTRICT, related_name="documents")
    document_type = models.CharField(max_length=64)
    storage_object_key = models.TextField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateField(null=True, blank=True)
    is_critical = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vehicle_documents"
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "document_type", "sha256"],
                name="uq_vehicle_document_hash",
            )
        ]
        indexes = [models.Index(fields=["vehicle", "status", "expires_at"], name="ix_vehicle_doc_validity")]


class Driver(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        EXPIRED = "expired", "Expired"

    operator = models.ForeignKey(TransportOperator, on_delete=models.RESTRICT, related_name="drivers")
    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    full_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=20, null=True, blank=True)
    license_number_ciphertext = models.BinaryField()
    license_last4 = models.CharField(max_length=8, null=True, blank=True)
    license_expires_at = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "drivers"
        indexes = [models.Index(fields=["operator", "status"], name="ix_driver_operator_status")]
        ordering = ["full_name"]
