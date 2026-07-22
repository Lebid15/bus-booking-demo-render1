from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from bookings.models import Booking
from common.models import OutboxEvent
from identity.models import User
from notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationEscalation,
    NotificationTemplate,
)
from notifications.services import (
    create_notifications_for_event,
    dispatch_outbox_events,
    process_delivery,
    seed_default_templates,
)
from support.models import SupportCase
from trips.models import TripChange, TripChangeResponse

from .test_e13_policies_configuration import _confirmed_booking

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _booking_event(booking: Booking) -> OutboxEvent:
    return OutboxEvent.objects.get(
        aggregate_type="booking",
        aggregate_id=booking.id,
        event_type="booking.created",
    )


@override_settings(
    NOTIFICATION_FORCE_FAILURE_CHANNELS="email",
    NOTIFICATION_RETRY_BASE_SECONDS=0,
    NOTIFICATION_MAX_ATTEMPTS=4,
)
def test_e15_ac01_booking_remains_successful_when_email_fails_and_retry_is_scheduled() -> None:
    booking, _ = _confirmed_booking()
    original_status = booking.status

    assert dispatch_outbox_events() >= 1
    email = NotificationDelivery.objects.get(
        notification__booking=booking,
        channel=NotificationTemplate.Channel.EMAIL,
        attempt_no=1,
    )
    assert process_delivery(email.id) is False

    booking.refresh_from_db()
    assert booking.status == original_status
    assert NotificationDelivery.objects.filter(
        notification=email.notification,
        channel=NotificationTemplate.Channel.EMAIL,
        attempt_no=2,
        status=NotificationDelivery.Status.QUEUED,
    ).exists()


def test_e15_ac02_republished_event_does_not_duplicate_channel_and_template_version() -> None:
    booking, _ = _confirmed_booking()
    event = _booking_event(booking)
    seed_default_templates()

    first = create_notifications_for_event(event)
    duplicate = OutboxEvent.objects.create(
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        event_type=event.event_type,
        payload=event.payload,
    )
    second = create_notifications_for_event(duplicate)

    assert {item.id for item in first} == {item.id for item in second}
    assert Notification.objects.filter(booking=booking, event_type="booking.created").count() == 2
    assert NotificationDelivery.objects.filter(notification__booking=booking).count() == 2


def test_e15_ac03_material_change_notification_requires_explicit_response_and_silence_does_not_accept() -> None:
    booking, _ = _confirmed_booking()
    actor = booking.trip.created_by
    change = TripChange.objects.create(
        trip=booking.trip,
        change_type=TripChange.ChangeType.TIME,
        classification=TripChange.Classification.MATERIAL,
        previous_snapshot={"departure": "old"},
        new_snapshot={"departure": "new"},
        response_deadline_at=timezone.now() + timedelta(hours=12),
        created_by=actor,
    )
    response = TripChangeResponse.objects.create(change=change, booking=booking)
    event = OutboxEvent.objects.create(
        aggregate_type="trip_change",
        aggregate_id=change.id,
        event_type="notification.requested",
        payload={
            "template": "trip_material_change_response_required",
            "trip_id": booking.trip.public_id,
            "booking_id": booking.public_id,
            "change_id": str(change.id),
        },
    )

    notifications = create_notifications_for_event(event)
    response.refresh_from_db()

    assert response.status == TripChangeResponse.Status.PENDING
    assert notifications
    assert all(item.action_required for item in notifications)
    assert all(item.action_url == "/manage-booking" for item in notifications)


@override_settings(
    NOTIFICATION_FORCE_FAILURE_CHANNELS="email",
    NOTIFICATION_MAX_ATTEMPTS=1,
)
def test_e15_ac04_exhausted_critical_channel_creates_sms_fallback_and_human_escalation() -> None:
    booking, _ = _confirmed_booking()
    create_notifications_for_event(_booking_event(booking))
    email = NotificationDelivery.objects.get(
        notification__booking=booking,
        channel=NotificationTemplate.Channel.EMAIL,
        attempt_no=1,
    )

    assert process_delivery(email.id) is False

    assert Notification.objects.filter(
        booking=booking,
        template__channel=NotificationTemplate.Channel.SMS,
    ).exists()
    escalation = NotificationEscalation.objects.select_related("support_case").get(notification=email.notification)
    assert escalation.support_case is not None
    assert escalation.support_case.priority == SupportCase.Priority.P1
    assert escalation.support_case.category == "notification_delivery_failure"


def test_e15_ac05_user_language_and_latest_published_template_version_are_used() -> None:
    booking, _ = _confirmed_booking()
    user = User.objects.create_user(
        full_name="English Passenger",
        email=f"english-{uuid.uuid4().hex[:8]}@example.com",
        preferred_language="en",
    )
    booking.customer_user = user
    booking.save(update_fields=["customer_user", "updated_at"])
    seed_default_templates()
    NotificationTemplate.objects.create(
        code="booking_created_unpaid",
        channel=NotificationTemplate.Channel.EMAIL,
        language="en",
        version=2,
        subject_template="Booking {pnr} — version two",
        body_template="Latest English template for {pnr}.",
        status=NotificationTemplate.Status.PUBLISHED,
        effective_from=timezone.now() - timedelta(minutes=1),
    )

    notifications = create_notifications_for_event(_booking_event(booking))
    email = next(item for item in notifications if item.template.channel == NotificationTemplate.Channel.EMAIL)

    assert email.language == "en"
    assert email.template.version == 2
    assert email.rendered_subject == f"Booking {booking.pnr} — version two"
    assert email.rendered_body == f"Latest English template for {booking.pnr}."
