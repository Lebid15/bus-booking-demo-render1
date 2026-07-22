from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import UUIDPrimaryKeyModel


class ImmutableRecordMixin(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if not self._state.adding:
            raise RuntimeError(f"{type(self).__name__} is append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"{type(self).__name__} is append-only")


class BoardingEvent(ImmutableRecordMixin, UUIDPrimaryKeyModel):
    class EventType(models.TextChoices):
        ARRIVED = "arrived", "Arrived"
        VERIFIED = "verified", "Verified"
        BOARDED = "boarded", "Boarded"
        REVERSED = "reversed", "Reversed"
        DENIED = "denied", "Denied"
        NO_SHOW = "no_show", "No-show"
        MANUAL_CHECK = "manual_check", "Manual check"

    trip = models.ForeignKey("trips.Trip", on_delete=models.RESTRICT, related_name="boarding_events")
    passenger = models.ForeignKey(
        "bookings.BookingPassenger",
        on_delete=models.RESTRICT,
        related_name="boarding_events",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="boarding_events",
    )
    event_type = models.CharField(max_length=24, choices=EventType.choices)
    occurred_at = models.DateTimeField()
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="boarding_events",
    )
    device = models.ForeignKey(
        "identity.UserDevice",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="boarding_events",
    )
    offline_event_id = models.CharField(max_length=80, null=True, blank=True)
    reason_code = models.CharField(max_length=80, null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "boarding_events"
        constraints = [
            models.UniqueConstraint(
                fields=["device", "offline_event_id"],
                condition=Q(offline_event_id__isnull=False),
                name="uq_boarding_device_offline_event",
            )
        ]
        indexes = [
            models.Index(fields=["trip", "occurred_at"], name="ix_board_event_trip_time"),
            models.Index(fields=["passenger", "occurred_at"], name="ix_board_event_pass_time"),
        ]
        ordering = ["occurred_at", "id"]


class TripManifest(ImmutableRecordMixin, UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        BOARDING_CLOSED = "boarding_closed", "Boarding closed"
        FINAL = "final", "Final"

    trip = models.ForeignKey("trips.Trip", on_delete=models.RESTRICT, related_name="manifests")
    version_no = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    manifest_json = models.JSONField()
    sha256 = models.CharField(max_length=64)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="generated_trip_manifests",
    )

    class Meta:
        db_table = "trip_manifests"
        constraints = [models.UniqueConstraint(fields=["trip", "version_no"], name="uq_trip_manifest_version")]
        indexes = [models.Index(fields=["trip", "-version_no"], name="ix_manifest_trip_version")]
        ordering = ["-version_no"]


class OfflineBoardingPackage(UUIDPrimaryKeyModel):
    trip = models.ForeignKey("trips.Trip", on_delete=models.RESTRICT, related_name="offline_packages")
    manifest = models.ForeignKey(TripManifest, on_delete=models.RESTRICT, related_name="offline_packages")
    device = models.ForeignKey(
        "identity.UserDevice",
        on_delete=models.RESTRICT,
        related_name="offline_boarding_packages",
    )
    trip_version = models.PositiveIntegerField()
    package_hash = models.CharField(max_length=64, unique=True)
    ciphertext = models.BinaryField()
    signature = models.BinaryField()
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="created_offline_boarding_packages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "offline_boarding_packages"
        indexes = [models.Index(fields=["trip", "expires_at"], name="ix_offline_pkg_trip_expiry")]


class BoardingSyncConflict(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"

    package = models.ForeignKey(
        OfflineBoardingPackage,
        on_delete=models.RESTRICT,
        related_name="conflicts",
    )
    offline_event_id = models.CharField(max_length=80)
    passenger = models.ForeignKey(
        "bookings.BookingPassenger",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="boarding_sync_conflicts",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="boarding_sync_conflicts",
    )
    conflict_type = models.CharField(max_length=80)
    event_payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "boarding_sync_conflicts"
        constraints = [
            models.UniqueConstraint(
                fields=["package", "offline_event_id"],
                name="uq_offline_package_conflict_event",
            )
        ]
        indexes = [models.Index(fields=["package", "status"], name="ix_offline_conflict_status")]


class BoardingCorrectionApproval(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        APPROVED = "approved", "Approved"
        USED = "used", "Used"
        REVOKED = "revoked", "Revoked"

    passenger = models.ForeignKey(
        "bookings.BookingPassenger",
        on_delete=models.RESTRICT,
        related_name="boarding_correction_approvals",
    )
    reason_code = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.RESTRICT,
        related_name="approved_boarding_corrections",
    )
    approved_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "boarding_correction_approvals"
