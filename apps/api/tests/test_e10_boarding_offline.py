from __future__ import annotations

import hashlib
import threading
import uuid
from datetime import timedelta

import pytest
from django import db
from django.db import connection
from django.test import RequestFactory, override_settings
from django.utils import timezone

from auditlog.models import AuditLog
from boarding.models import (
    BoardingCorrectionApproval,
    BoardingEvent,
    BoardingSyncConflict,
    OfflineBoardingPackage,
    TripManifest,
)
from boarding.services import (
    create_offline_package,
    execute_boarding_command,
    mark_due_no_shows,
    serialize_manifest,
    sync_offline_events,
)
from bookings.models import Booking, BookingPassenger
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from identity.models import User, UserDevice, UserSession
from organizations.services import OfficeContext
from tickets.models import Ticket
from tickets.services import ticket_qr_data
from trips.models import Trip
from trips.services import command_trip

from .test_e08_tickets_self_service import _confirmed_booking

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _request(user: User, *, key: str = "e10-boarding-key"):
    request = RequestFactory().post(
        "/v1/office/trips/test/boarding",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="203.0.113.70",
    )
    request.user = user
    return request


def _environment() -> tuple[Booking, dict[str, object], User, OfficeContext, UserSession]:
    booking, created = _confirmed_booking()
    trip = booking.trip
    actor = trip.created_by
    membership = actor.office_memberships.get(office=trip.office)
    context = OfficeContext(
        membership=membership,
        permissions=frozenset({"office.trip.manage", "office.boarding.scan"}),
    )
    device = UserDevice.objects.create(
        user=actor,
        device_fingerprint_hash=hashlib.sha256(uuid.uuid4().bytes).digest(),
        label="جهاز البوابة",
        trusted_at=timezone.now(),
    )
    session = UserSession.objects.create(
        user=actor,
        device=device,
        token_hash=hashlib.sha256(uuid.uuid4().bytes).digest(),
        expires_at=timezone.now() + timedelta(hours=8),
        mfa_verified_at=timezone.now(),
    )
    trip.boarding_open_at = timezone.now() - timedelta(minutes=5)
    trip.boarding_close_at = timezone.now() + timedelta(minutes=30)
    trip.save(update_fields=["boarding_open_at", "boarding_close_at"])
    trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-open-boarding"),
        trip_id=trip.public_id,
        data={"command": "open_boarding", "version": trip.version},
    )
    booking.trip = trip
    return booking, created, actor, context, session


def _active_ticket(booking: Booking) -> Ticket:
    return Ticket.objects.select_related("passenger", "seat_assignment__trip_seat").get(
        booking=booking,
        status=Ticket.Status.ACTIVE,
    )


def test_e10_ac02_manual_check_boards_with_reason_and_audit() -> None:
    booking, _, actor, context, session = _environment()
    passenger = booking.passengers.get()
    result = execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-manual-board"),
        trip_id=booking.trip.public_id,
        data={
            "command": "board",
            "passenger_id": passenger.id,
            "reason_code": "qr_reader_failed_identity_verified",
        },
    )
    passenger.refresh_from_db()
    assert result["boarding_status"] == BookingPassenger.BoardingStatus.BOARDED
    assert passenger.boarding_status == BookingPassenger.BoardingStatus.BOARDED
    event = BoardingEvent.objects.get(passenger=passenger)
    assert event.event_type == BoardingEvent.EventType.MANUAL_CHECK
    assert event.reason_code == "qr_reader_failed_identity_verified"
    assert AuditLog.objects.filter(action="office.boarding.board", object_id=passenger.id).exists()


def test_manual_boarding_without_reason_is_rejected_server_side() -> None:
    booking, _, actor, context, session = _environment()
    passenger = booking.passengers.get()
    with pytest.raises(DomainAPIException) as exc:
        execute_boarding_command(
            context=context,
            actor=actor,
            session=session,
            request=_request(actor, key="e10-manual-no-reason"),
            trip_id=booking.trip.public_id,
            data={"command": "board", "passenger_id": passenger.id},
        )
    assert exc.value.code == "BOARDING_REASON_REQUIRED"
    assert not BoardingEvent.objects.filter(passenger=passenger).exists()


def test_boarding_command_idempotency_replays_and_rejects_payload_reuse() -> None:
    booking, _, actor, context, session = _environment()
    ticket = _active_ticket(booking)
    qr = ticket_qr_data(ticket)
    key = "e10-command-idempotency"
    first = execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=key),
        trip_id=booking.trip.public_id,
        data={"command": "board", "ticket_qr": qr},
        idempotency_key=key,
    )
    replay = execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=key),
        trip_id=booking.trip.public_id,
        data={"command": "board", "ticket_qr": qr},
        idempotency_key=key,
    )
    assert replay == first
    assert BoardingEvent.objects.filter(passenger=ticket.passenger).count() == 1

    with pytest.raises(DomainAPIException) as exc:
        execute_boarding_command(
            context=context,
            actor=actor,
            session=session,
            request=_request(actor, key=key),
            trip_id=booking.trip.public_id,
            data={"command": "verify", "passenger_id": ticket.passenger_id},
            idempotency_key=key,
        )
    assert exc.value.code == "CONFLICT"


def test_boarding_qr_is_single_use_and_second_scan_is_rejected() -> None:
    booking, _, actor, context, session = _environment()
    ticket = _active_ticket(booking)
    qr = ticket_qr_data(ticket)
    first = execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-first-scan"),
        trip_id=booking.trip.public_id,
        data={"command": "board", "ticket_qr": qr},
    )
    assert first["ticket_status"] == Ticket.Status.USED
    with pytest.raises(DomainAPIException) as exc:
        execute_boarding_command(
            context=context,
            actor=actor,
            session=session,
            request=_request(actor, key="e10-second-scan"),
            trip_id=booking.trip.public_id,
            data={"command": "board", "ticket_qr": qr},
        )
    assert exc.value.code == "TICKET_ALREADY_USED"
    assert BoardingEvent.objects.filter(passenger=ticket.passenger).count() == 1


def test_boarding_state_cannot_regress_after_successful_scan() -> None:
    booking, _, actor, context, session = _environment()
    ticket = _active_ticket(booking)
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-board-state"),
        trip_id=booking.trip.public_id,
        data={"command": "board", "ticket_qr": ticket_qr_data(ticket)},
    )
    with pytest.raises(DomainAPIException) as exc:
        execute_boarding_command(
            context=context,
            actor=actor,
            session=session,
            request=_request(actor, key="e10-regress-state"),
            trip_id=booking.trip.public_id,
            data={"command": "arrive", "passenger_id": ticket.passenger_id},
        )
    assert exc.value.code == "STATE_TRANSITION_NOT_ALLOWED"
    ticket.passenger.refresh_from_db()
    assert ticket.passenger.boarding_status == BookingPassenger.BoardingStatus.BOARDED


def test_e10_ac03_no_show_job_skips_denied_boarding_review() -> None:
    booking, _, actor, context, session = _environment()
    passenger = booking.passengers.get()
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-arrive-before-deny"),
        trip_id=booking.trip.public_id,
        data={"command": "arrive", "passenger_id": passenger.id},
    )
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-deny"),
        trip_id=booking.trip.public_id,
        data={"command": "deny", "passenger_id": passenger.id, "reason_code": "ticket_disputed"},
    )
    trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-close-denied"),
        trip_id=booking.trip.public_id,
        data={"command": "close_boarding", "version": booking.trip.version},
    )
    now = timezone.now()
    Trip.objects.filter(id=trip.id).update(
        scheduled_departure_at=now - timedelta(minutes=1),
        booking_close_at=now - timedelta(hours=2),
        boarding_open_at=now - timedelta(hours=1),
        boarding_close_at=now - timedelta(minutes=15),
    )
    assert mark_due_no_shows() == 0
    passenger.refresh_from_db()
    booking.refresh_from_db()
    assert passenger.boarding_status == BookingPassenger.BoardingStatus.DENIED
    assert booking.status == Booking.Status.DENIED_BOARDING_REVIEW


def test_due_no_show_marks_only_eligible_unarrived_passenger() -> None:
    booking, _, actor, context, _ = _environment()
    trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-close-normal"),
        trip_id=booking.trip.public_id,
        data={"command": "close_boarding", "version": booking.trip.version},
    )
    now = timezone.now()
    Trip.objects.filter(id=trip.id).update(
        scheduled_departure_at=now - timedelta(minutes=1),
        booking_close_at=now - timedelta(hours=2),
        boarding_open_at=now - timedelta(hours=1),
        boarding_close_at=now - timedelta(minutes=15),
    )
    assert mark_due_no_shows() == 1
    passenger = booking.passengers.get()
    passenger.refresh_from_db()
    booking.refresh_from_db()
    assert passenger.boarding_status == BookingPassenger.BoardingStatus.NO_SHOW
    assert booking.status == Booking.Status.NO_SHOW
    event = BoardingEvent.objects.get(passenger=passenger, event_type=BoardingEvent.EventType.NO_SHOW)
    assert AuditLog.objects.filter(action="system.boarding.no_show", object_id=passenger.id).exists()
    assert OutboxEvent.objects.filter(aggregate_id=event.id, event_type="boarding.no_show").exists()


@override_settings(OFFLINE_BOARDING_PACKAGE_TTL_SECONDS=3600)
def test_e10_ac04_offline_sync_is_idempotent_and_surfaces_conflicts() -> None:
    booking, _, actor, context, session = _environment()
    ticket = _active_ticket(booking)
    package_key = "e10-package-idempotency"
    package = create_offline_package(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=package_key),
        trip_id=booking.trip.public_id,
        idempotency_key=package_key,
    )
    package_replay = create_offline_package(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=package_key),
        trip_id=booking.trip.public_id,
        idempotency_key=package_key,
    )
    assert package_replay["package_hash"] == package["package_hash"]
    assert OfflineBoardingPackage.objects.filter(trip=booking.trip).count() == 1
    event = {
        "command": "board",
        "ticket_qr": ticket_qr_data(ticket),
        "offline_event_id": "device-event-001",
        "occurred_at": timezone.now(),
    }
    sync_key = "e10-sync-idempotency"
    first = sync_offline_events(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=sync_key),
        trip_id=booking.trip.public_id,
        package_hash=str(package["package_hash"]),
        events=[event],
        idempotency_key=sync_key,
    )
    replay = sync_offline_events(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key=sync_key),
        trip_id=booking.trip.public_id,
        package_hash=str(package["package_hash"]),
        events=[event],
        idempotency_key=sync_key,
    )
    duplicate = sync_offline_events(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-sync-new-request"),
        trip_id=booking.trip.public_id,
        package_hash=str(package["package_hash"]),
        events=[event],
        idempotency_key="e10-sync-new-request",
    )
    assert first == {"accepted": 1, "duplicates": 0, "conflicts": [], "purge_required": True}
    assert replay == first
    assert duplicate["accepted"] == 0
    assert duplicate["duplicates"] == 1
    assert BoardingEvent.objects.filter(offline_event_id="device-event-001").count() == 1

    conflict_event = {
        "command": "reverse",
        "passenger_id": str(ticket.passenger_id),
        "reason_code": "offline_reverse_forbidden",
        "offline_event_id": "device-event-002",
    }
    conflict_result = sync_offline_events(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-sync-conflict"),
        trip_id=booking.trip.public_id,
        package_hash=str(package["package_hash"]),
        events=[conflict_event],
        idempotency_key="e10-sync-conflict",
    )
    assert conflict_result["accepted"] == 0
    assert conflict_result["conflicts"][0]["type"] == "offline_command_not_allowed"
    assert BoardingSyncConflict.objects.filter(offline_event_id="device-event-002").exists()


def test_e10_ac05_reverse_after_departure_requires_admin_approval() -> None:
    booking, _, actor, context, session = _environment()
    ticket = _active_ticket(booking)
    execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-board-before-depart"),
        trip_id=booking.trip.public_id,
        data={"command": "board", "ticket_qr": ticket_qr_data(ticket)},
    )
    trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-close-before-depart"),
        trip_id=booking.trip.public_id,
        data={"command": "close_boarding", "version": booking.trip.version},
    )
    trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-depart"),
        trip_id=trip.public_id,
        data={"command": "depart", "version": trip.version},
    )
    with pytest.raises(DomainAPIException) as exc:
        execute_boarding_command(
            context=context,
            actor=actor,
            session=session,
            request=_request(actor, key="e10-reverse-denied"),
            trip_id=trip.public_id,
            data={
                "command": "reverse",
                "passenger_id": ticket.passenger_id,
                "reason_code": "operator_correction",
            },
        )
    assert exc.value.code == "BOARDING_CORRECTION_APPROVAL_REQUIRED"

    platform_admin = User.objects.create_user(
        full_name="مدير المنصة",
        email=f"platform-{uuid.uuid4()}@example.com",
        password="SecurePass!234",
        is_platform_staff=True,
    )
    approval = BoardingCorrectionApproval.objects.create(
        passenger=ticket.passenger,
        reason_code="verified_operational_error",
        approved_by=platform_admin,
    )
    result = execute_boarding_command(
        context=context,
        actor=actor,
        session=session,
        request=_request(actor, key="e10-reverse-approved"),
        trip_id=trip.public_id,
        data={
            "command": "reverse",
            "passenger_id": ticket.passenger_id,
            "reason_code": "operator_correction",
            "correction_approval_id": approval.id,
        },
    )
    approval.refresh_from_db()
    assert result["boarding_status"] == BookingPassenger.BoardingStatus.BOARDED_REVERSED
    assert approval.status == BoardingCorrectionApproval.Status.USED


def test_e10_ac06_closed_and_final_manifests_are_hashed_and_tamper_evident() -> None:
    booking, _, actor, context, _ = _environment()
    closed_trip = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-close-manifest"),
        trip_id=booking.trip.public_id,
        data={"command": "close_boarding", "version": booking.trip.version},
    )
    closed = TripManifest.objects.get(trip=closed_trip, status=TripManifest.Status.BOARDING_CLOSED)
    payload = serialize_manifest(closed)
    assert payload["sha256"] == hashlib.sha256(
        __import__("json").dumps(
            payload["manifest"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    with pytest.raises(RuntimeError):
        closed.save()

    departed = command_trip(
        context=context,
        actor=actor,
        request=_request(actor, key="e10-depart-manifest"),
        trip_id=closed_trip.public_id,
        data={"command": "depart", "version": closed_trip.version},
    )
    final = TripManifest.objects.get(trip=departed, status=TripManifest.Status.FINAL)
    assert final.version_no == closed.version_no + 1
    TripManifest.objects.filter(id=final.id).update(manifest_json={"tampered": True})
    final.refresh_from_db()
    with pytest.raises(DomainAPIException) as exc:
        serialize_manifest(final)
    assert exc.value.code == "MANIFEST_INTEGRITY_FAILED"


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_e10_ac01_postgresql_concurrent_qr_scan_records_boarded_once() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL row-lock concurrency gate")
    booking, _, actor, context, session = _environment()
    qr = ticket_qr_data(_active_ticket(booking))
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker(index: int) -> None:
        db.connections.close_all()
        barrier.wait()
        try:
            execute_boarding_command(
                context=context,
                actor=actor,
                session=session,
                request=_request(actor, key=f"e10-concurrent-{index}"),
                trip_id=booking.trip.public_id,
                data={"command": "board", "ticket_qr": qr},
            )
            outcomes.append("ok")
        except DomainAPIException as exc:
            outcomes.append(exc.code)
        finally:
            db.connections.close_all()

    threads = [threading.Thread(target=worker, args=(1,)), threading.Thread(target=worker, args=(2,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("ok") == 1
    assert outcomes.count("TICKET_ALREADY_USED") == 1
    assert BoardingEvent.objects.filter(passenger__booking=booking).count() == 1
