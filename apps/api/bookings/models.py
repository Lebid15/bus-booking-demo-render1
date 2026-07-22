from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from common.ids import generate_public_id
from common.models import UUIDPrimaryKeyModel
from organizations.models import Office, OfficeBranch


def generate_pnr() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Booking(UUIDPrimaryKeyModel):
    class Source(models.TextChoices):
        PUBLIC_WEB = "public_web", "Public web"
        OFFICE = "office", "Office"
        PHONE = "phone", "Phone"
        IMPORT = "import", "Import"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLATION_PENDING = "cancellation_pending", "Cancellation pending"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No-show"
        DENIED_BOARDING_REVIEW = "denied_boarding_review", "Denied boarding review"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PENDING_VERIFICATION = "pending_verification", "Pending verification"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"
        DISPUTED = "disputed", "Disputed"

    public_id = models.CharField(max_length=26, unique=True, default=generate_public_id, editable=False)
    pnr = models.CharField(max_length=12, unique=True, default=generate_pnr, editable=False)
    office = models.ForeignKey(Office, on_delete=models.RESTRICT, related_name="bookings")
    branch = models.ForeignKey(OfficeBranch, on_delete=models.RESTRICT, related_name="bookings")
    trip = models.ForeignKey("trips.Trip", on_delete=models.RESTRICT, related_name="bookings")
    customer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="bookings",
    )
    source = models.CharField(max_length=24, choices=Source.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    payment_status = models.CharField(
        max_length=24,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    contact_name = models.CharField(max_length=160)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    refunded_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    payment_deadline_at = models.DateTimeField(null=True, blank=True)
    policy_snapshot = models.JSONField(default=dict)
    pricing_snapshot = models.JSONField(default=dict)
    commission_snapshot = models.JSONField(default=dict)
    terms_version_ids = models.JSONField(default=list)
    manage_token_hash = models.BinaryField(unique=True)
    version = models.PositiveIntegerField(default=1)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="created_bookings",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal_amount__gte=0)
                & Q(discount_amount__gte=0)
                & Q(fee_amount__gte=0)
                & Q(total_amount__gte=0),
                name="ck_booking_nonnegative_totals",
            ),
            models.CheckConstraint(
                condition=Q(total_amount=F("subtotal_amount") - F("discount_amount") + F("fee_amount")),
                name="ck_booking_total_formula",
            ),
            models.CheckConstraint(
                condition=Q(paid_amount__gte=0) & Q(refunded_amount__gte=0) & Q(refunded_amount__lte=F("paid_amount")),
                name="ck_booking_payment_totals",
            ),
        ]
        indexes = [
            models.Index(fields=["office", "-created_at"], name="ix_booking_office_created"),
            models.Index(fields=["trip", "status"], name="ix_booking_trip_status"),
            models.Index(fields=["contact_phone"], name="ix_booking_contact_phone"),
        ]


class BookingPassenger(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    class PassengerType(models.TextChoices):
        ADULT = "adult", "Adult"
        CHILD = "child", "Child"
        INFANT = "infant", "Infant"

    class BoardingStatus(models.TextChoices):
        NOT_ARRIVED = "not_arrived", "Not arrived"
        ARRIVED = "arrived", "Arrived"
        VERIFIED = "verified", "Verified"
        BOARDED = "boarded", "Boarded"
        BOARDED_REVERSED = "boarded_reversed", "Boarded reversed"
        DENIED = "denied", "Denied"
        NO_SHOW = "no_show", "No-show"

    booking = models.ForeignKey(Booking, on_delete=models.RESTRICT, related_name="passengers")
    sequence_no = models.PositiveSmallIntegerField()
    full_name = models.CharField(max_length=160)
    gender = models.CharField(max_length=12, choices=Gender.choices)
    passenger_type = models.CharField(
        max_length=16,
        choices=PassengerType.choices,
        default=PassengerType.ADULT,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    nationality_code = models.CharField(max_length=2, null=True, blank=True)
    identity_type = models.CharField(max_length=24, null=True, blank=True)
    identity_number_normalized = models.CharField(max_length=80, null=True, blank=True)
    boarding_status = models.CharField(
        max_length=28,
        choices=BoardingStatus.choices,
        default=BoardingStatus.NOT_ARRIVED,
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_passengers"
        constraints = [models.UniqueConstraint(fields=["booking", "sequence_no"], name="uq_booking_passenger_sequence")]


class BookingChange(UUIDPrimaryKeyModel):
    class ChangeType(models.TextChoices):
        PASSENGER_REPLACED = "passenger_replaced", "Passenger replaced"
        SEAT_CHANGED = "seat_changed", "Seat changed"
        PASSENGER_CANCELLED = "passenger_cancelled", "Passenger cancelled"
        BOOKING_CANCELLED = "booking_cancelled", "Booking cancelled"

    booking = models.ForeignKey(Booking, on_delete=models.RESTRICT, related_name="changes")
    passenger = models.ForeignKey(
        BookingPassenger,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="changes",
    )
    change_type = models.CharField(max_length=32, choices=ChangeType.choices)
    reason_code = models.CharField(max_length=80, null=True, blank=True)
    before_snapshot = models.JSONField(default=dict)
    after_snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="booking_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "booking_changes"
        indexes = [models.Index(fields=["booking", "-created_at"], name="ix_booking_change_created")]


class SeatAssignment(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        MOVED = "moved", "Moved"
        CANCELLED = "cancelled", "Cancelled"

    trip = models.ForeignKey("trips.Trip", on_delete=models.RESTRICT, related_name="seat_assignments")
    booking = models.ForeignKey(Booking, on_delete=models.RESTRICT, related_name="seat_assignments")
    passenger = models.ForeignKey(
        BookingPassenger,
        on_delete=models.RESTRICT,
        related_name="seat_assignments",
    )
    trip_seat = models.ForeignKey(
        "trips.TripSeat",
        on_delete=models.RESTRICT,
        related_name="assignments",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    price_amount = models.DecimalField(max_digits=18, decimal_places=2)
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="supersedes",
    )

    class Meta:
        db_table = "seat_assignments"
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "trip_seat"],
                condition=Q(status="active"),
                name="uq_active_seat_assignment",
            ),
            models.UniqueConstraint(
                fields=["passenger"],
                condition=Q(status="active"),
                name="uq_active_passenger_assignment",
            ),
            models.CheckConstraint(condition=Q(price_amount__gte=0), name="ck_assignment_price"),
        ]
