from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel
from fleet.models import Driver, SeatLayout, SeatLayoutSeat, Vehicle
from geography.models import Location, Route
from organizations.models import Office, OfficeBranch, TransportOperator


class Trip(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHED = "published", "Published"
        BOOKING_OPEN = "booking_open", "Booking open"
        BOARDING_OPEN = "boarding_open", "Boarding open"
        BOARDING_CLOSED = "boarding_closed", "Boarding closed"
        DEPARTED = "departed", "Departed"
        ARRIVED = "arrived", "Arrived"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        INTERRUPTED = "interrupted", "Interrupted"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="trips")
    branch = models.ForeignKey(OfficeBranch, on_delete=models.RESTRICT, related_name="trips")
    operator = models.ForeignKey(TransportOperator, on_delete=models.RESTRICT, related_name="trips")
    route = models.ForeignKey(Route, on_delete=models.RESTRICT, related_name="trips")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.RESTRICT, related_name="trips")
    driver = models.ForeignKey(
        Driver,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="trips",
    )
    seat_layout = models.ForeignKey(SeatLayout, on_delete=models.RESTRICT, related_name="trips")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    scheduled_departure_at = models.DateTimeField()
    scheduled_arrival_at = models.DateTimeField(null=True, blank=True)
    actual_departure_at = models.DateTimeField(null=True, blank=True)
    actual_arrival_at = models.DateTimeField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    base_price = models.DecimalField(max_digits=18, decimal_places=2)
    booking_open_at = models.DateTimeField(null=True, blank=True)
    booking_close_at = models.DateTimeField(null=True, blank=True)
    boarding_open_at = models.DateTimeField(null=True, blank=True)
    boarding_close_at = models.DateTimeField(null=True, blank=True)
    policy_snapshot = models.JSONField(default=dict)
    pricing_snapshot = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_trips",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "trips"
        constraints = [
            models.CheckConstraint(
                condition=Q(scheduled_arrival_at__isnull=True)
                | Q(scheduled_arrival_at__gt=models.F("scheduled_departure_at")),
                name="ck_trip_arrival_after_departure",
            ),
            models.CheckConstraint(condition=Q(base_price__gte=0), name="ck_trip_base_price"),
            models.CheckConstraint(
                condition=Q(booking_close_at__isnull=True)
                | Q(booking_close_at__lte=models.F("scheduled_departure_at")),
                name="ck_trip_booking_close_before_departure",
            ),
        ]
        indexes = [
            models.Index(
                fields=["route", "scheduled_departure_at", "status"],
                name="ix_trip_search",
            ),
            models.Index(
                fields=["office", "scheduled_departure_at"],
                name="ix_trip_office_departure",
            ),
        ]
        ordering = ["scheduled_departure_at", "public_id"]


class TripStop(UUIDPrimaryKeyModel):
    class StopType(models.TextChoices):
        BOARDING = "boarding", "Boarding"
        DROPOFF = "dropoff", "Drop-off"
        BOTH = "both", "Both"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="stops")
    sequence_no = models.PositiveSmallIntegerField()
    location = models.ForeignKey(Location, on_delete=models.RESTRICT, related_name="trip_stops")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    actual_at = models.DateTimeField(null=True, blank=True)
    stop_type = models.CharField(max_length=20, choices=StopType.choices)

    class Meta:
        db_table = "trip_stops"
        constraints = [
            models.UniqueConstraint(fields=["trip", "sequence_no"], name="uq_trip_stop_sequence"),
            models.UniqueConstraint(fields=["trip", "location"], name="uq_trip_stop_location"),
            models.CheckConstraint(condition=Q(sequence_no__gt=0), name="ck_trip_stop_sequence"),
        ]
        ordering = ["sequence_no"]


class TripSeat(UUIDPrimaryKeyModel):
    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="seats")
    layout_seat = models.ForeignKey(
        SeatLayoutSeat,
        on_delete=models.RESTRICT,
        related_name="trip_seats",
    )
    seat_code = models.CharField(max_length=12)
    seat_type = models.CharField(max_length=20)
    sellable = models.BooleanField(default=True)
    blocked_reason = models.CharField(max_length=160, null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    inventory_version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = "trip_seats"
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "layout_seat"], condition=Q(is_current=True), name="uq_current_trip_layout_seat"
            ),
            models.UniqueConstraint(
                fields=["trip", "seat_code"], condition=Q(is_current=True), name="uq_current_trip_seat_code"
            ),
        ]
        indexes = [
            models.Index(fields=["trip", "is_current", "sellable"], name="ix_trip_current_sellable"),
            models.Index(fields=["trip", "inventory_version"], name="ix_trip_inventory_version"),
        ]
        ordering = ["layout_seat__row_no", "layout_seat__column_no", "seat_code"]


class SeatHold(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONSUMED = "consumed", "Consumed"
        EXPIRED = "expired", "Expired"
        RELEASED = "released", "Released"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="seat_holds")
    trip_seat = models.ForeignKey(TripSeat, on_delete=models.RESTRICT, related_name="holds")
    hold_token_hash = models.BinaryField(unique=True)
    owner_session = models.ForeignKey(
        "identity.UserSession",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="seat_holds",
    )
    owner_booking_draft_id = models.UUIDField(null=True, blank=True)
    quote_version = models.PositiveIntegerField(default=1)
    quote_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "seat_holds"
        constraints = [
            models.CheckConstraint(condition=Q(expires_at__gt=models.F("created_at")), name="ck_hold_expiry"),
            models.UniqueConstraint(
                fields=["trip_seat"],
                condition=Q(status="active"),
                name="uq_active_hold_per_seat",
            ),
        ]
        indexes = [
            models.Index(
                fields=["expires_at"],
                condition=Q(status="active"),
                name="ix_hold_expiry",
            ),
            models.Index(
                fields=["owner_booking_draft_id", "status"],
                name="ix_hold_batch_status",
            ),
        ]


class TripChange(UUIDPrimaryKeyModel):
    class Classification(models.TextChoices):
        MINOR = "minor", "Minor"
        MATERIAL = "material", "Material"

    class ChangeType(models.TextChoices):
        TIME = "time", "Time"
        PRICE = "price", "Price"
        VEHICLE = "vehicle", "Vehicle"
        ROUTE = "route", "Route"
        MULTIPLE = "multiple", "Multiple"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="changes")
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    classification = models.CharField(max_length=20, choices=Classification.choices)
    previous_snapshot = models.JSONField(default=dict)
    new_snapshot = models.JSONField(default=dict)
    response_deadline_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="trip_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trip_changes"
        ordering = ["-created_at"]


class TripChangeResponse(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        ALTERNATIVE_REQUESTED = "alternative_requested", "Alternative requested"
        REFUND_REQUESTED = "refund_requested", "Refund requested"
        RESOLVED = "resolved", "Resolved"

    change = models.ForeignKey(TripChange, on_delete=models.RESTRICT, related_name="responses")
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="trip_change_responses",
    )
    status = models.CharField(max_length=28, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trip_change_responses"
        constraints = [models.UniqueConstraint(fields=["change", "booking"], name="uq_trip_change_booking")]


class TripCancellationAction(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ALTERNATIVE_OFFERED = "alternative_offered", "Alternative offered"
        REFUND_STARTED = "refund_started", "Refund started"
        RESOLVED = "resolved", "Resolved"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="cancellation_actions")
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="trip_cancellation_actions",
    )
    reason_code = models.CharField(max_length=80)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trip_cancellation_actions"
        constraints = [models.UniqueConstraint(fields=["trip", "booking"], name="uq_trip_cancellation_booking")]


class TripOperationalIssue(UUIDPrimaryKeyModel):
    class IssueType(models.TextChoices):
        URGENT_CASE = "urgent_case", "Urgent case"
        MANIFEST_UNBALANCED = "manifest_unbalanced", "Manifest unbalanced"
        VEHICLE_UNAVAILABLE = "vehicle_unavailable", "Vehicle unavailable"
        DRIVER_UNAVAILABLE = "driver_unavailable", "Driver unavailable"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="operational_issues")
    issue_type = models.CharField(max_length=40, choices=IssueType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trip_operational_issues"
        indexes = [models.Index(fields=["trip", "status"], name="ix_trip_issue_status")]


class TripReallocationPlan(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PREVIEWED = "previewed", "Previewed"
        CONFLICTED = "conflicted", "Conflicted"
        APPLIED = "applied", "Applied"
        SUPERSEDED = "superseded", "Superseded"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="reallocation_plans")
    previous_vehicle = models.ForeignKey(
        Vehicle, on_delete=models.RESTRICT, related_name="previous_trip_reallocation_plans"
    )
    target_vehicle = models.ForeignKey(
        Vehicle, on_delete=models.RESTRICT, related_name="target_trip_reallocation_plans"
    )
    previous_layout = models.ForeignKey(
        SeatLayout, on_delete=models.RESTRICT, related_name="previous_trip_reallocation_plans"
    )
    target_layout = models.ForeignKey(
        SeatLayout, on_delete=models.RESTRICT, related_name="target_trip_reallocation_plans"
    )
    trip_version = models.PositiveIntegerField()
    source_inventory_version = models.PositiveIntegerField()
    target_inventory_version = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PREVIEWED)
    simulation = models.JSONField(default=dict)
    conflict_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name="created_trip_reallocation_plans"
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="applied_trip_reallocation_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "trip_reallocation_plans"
        indexes = [models.Index(fields=["trip", "status", "-created_at"], name="ix_trip_reallocation_status")]
        ordering = ["-created_at"]


class TripReallocationLine(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        CONFLICT = "conflict", "Conflict"
        APPLIED = "applied", "Applied"

    plan = models.ForeignKey(TripReallocationPlan, on_delete=models.RESTRICT, related_name="lines")
    passenger = models.ForeignKey(
        "bookings.BookingPassenger", on_delete=models.RESTRICT, related_name="trip_reallocation_lines"
    )
    old_assignment = models.ForeignKey(
        "bookings.SeatAssignment", on_delete=models.RESTRICT, related_name="trip_reallocation_lines"
    )
    old_seat_code = models.CharField(max_length=12)
    old_seat_type = models.CharField(max_length=20)
    target_layout_seat = models.ForeignKey(
        SeatLayoutSeat, null=True, blank=True, on_delete=models.RESTRICT, related_name="trip_reallocation_lines"
    )
    target_seat_code = models.CharField(max_length=12, null=True, blank=True)
    target_seat_type = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSED)
    conflict_code = models.CharField(max_length=80, null=True, blank=True)
    score = models.IntegerField(default=0)

    class Meta:
        db_table = "trip_reallocation_lines"
        constraints = [
            models.UniqueConstraint(fields=["plan", "passenger"], name="uq_reallocation_plan_passenger"),
            models.UniqueConstraint(
                fields=["plan", "target_layout_seat"],
                condition=Q(target_layout_seat__isnull=False),
                name="uq_reallocation_plan_target_seat",
            ),
        ]
        ordering = ["passenger__booking__pnr", "passenger__sequence_no"]


class TripInterruptionResolution(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SERVICE_COMPLETED = "service_completed", "Service completed"
        ALTERNATIVE_ACCEPTED = "alternative_accepted", "Alternative accepted"
        REFUND_STARTED = "refund_started", "Refund started"
        COMPENSATED = "compensated", "Compensated"

    trip = models.ForeignKey(Trip, on_delete=models.RESTRICT, related_name="interruption_resolutions")
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.RESTRICT, related_name="trip_interruption_resolutions"
    )
    status = models.CharField(max_length=28, choices=Status.choices, default=Status.PENDING)
    resolution_details = models.JSONField(default=dict)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="resolved_trip_interruptions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trip_interruption_resolutions"
        constraints = [models.UniqueConstraint(fields=["trip", "booking"], name="uq_trip_interruption_booking")]
        indexes = [models.Index(fields=["trip", "status"], name="ix_trip_interruption_status")]
