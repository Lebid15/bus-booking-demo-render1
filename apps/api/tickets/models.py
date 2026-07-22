from __future__ import annotations

from django.db import models
from django.db.models import Q

from common.models import UUIDPrimaryKeyModel


class Ticket(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        REVOKED = "revoked", "Revoked"
        USED = "used", "Used"
        EXPIRED = "expired", "Expired"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.RESTRICT,
        related_name="tickets",
    )
    passenger = models.ForeignKey(
        "bookings.BookingPassenger",
        on_delete=models.RESTRICT,
        related_name="tickets",
    )
    seat_assignment = models.ForeignKey(
        "bookings.SeatAssignment",
        on_delete=models.RESTRICT,
        related_name="tickets",
    )
    version_no = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    qr_token_hash = models.BinaryField(unique=True)
    qr_payload_signature = models.BinaryField()
    issued_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tickets"
        constraints = [
            models.UniqueConstraint(
                fields=["passenger", "version_no"],
                name="uq_ticket_passenger_version",
            ),
            models.UniqueConstraint(
                fields=["passenger"],
                condition=Q(status="active"),
                name="uq_active_ticket",
            ),
        ]
        indexes = [
            models.Index(fields=["booking", "status"], name="ix_ticket_booking_status"),
        ]
