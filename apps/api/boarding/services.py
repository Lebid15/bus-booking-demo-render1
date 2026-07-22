from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, cast

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from boarding.models import (
    BoardingCorrectionApproval,
    BoardingEvent,
    BoardingSyncConflict,
    OfflineBoardingPackage,
    TripManifest,
)
from bookings.models import Booking, BookingPassenger, SeatAssignment
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey, OutboxEvent
from identity.models import User, UserDevice, UserSession
from organizations.services import OfficeContext
from tickets.models import Ticket
from tickets.services import verify_ticket_qr
from trips.models import Trip

COMMAND_TO_STATUS = {
    "arrive": BookingPassenger.BoardingStatus.ARRIVED,
    "verify": BookingPassenger.BoardingStatus.VERIFIED,
    "board": BookingPassenger.BoardingStatus.BOARDED,
    "reverse": BookingPassenger.BoardingStatus.BOARDED_REVERSED,
    "deny": BookingPassenger.BoardingStatus.DENIED,
    "no_show": BookingPassenger.BoardingStatus.NO_SHOW,
}
COMMAND_TO_EVENT = {
    "arrive": BoardingEvent.EventType.ARRIVED,
    "verify": BoardingEvent.EventType.VERIFIED,
    "board": BoardingEvent.EventType.BOARDED,
    "reverse": BoardingEvent.EventType.REVERSED,
    "deny": BoardingEvent.EventType.DENIED,
    "no_show": BoardingEvent.EventType.NO_SHOW,
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        cls=DjangoJSONEncoder,
    ).encode()


def _request_fingerprint(payload: object) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _json_safe(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value, cls=DjangoJSONEncoder)))


def _begin_idempotency(
    *,
    scope_type: str,
    scope_id: uuid.UUID | str | None,
    key: str,
    payload: object,
    ttl: timedelta = timedelta(hours=24),
) -> tuple[IdempotencyKey, dict[str, Any] | None]:
    fingerprint = _request_fingerprint(payload)
    record = (
        IdempotencyKey.objects.select_for_update().filter(scope_type=scope_type, scope_id=scope_id, key=key).first()
    )
    if record is None:
        try:
            with transaction.atomic():
                record = IdempotencyKey.objects.create(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    key=key,
                    request_hash=fingerprint,
                    locked_until=timezone.now() + timedelta(seconds=45),
                    expires_at=timezone.now() + ttl,
                )
        except IntegrityError:
            record = IdempotencyKey.objects.select_for_update().get(scope_type=scope_type, scope_id=scope_id, key=key)
    if record.request_hash != fingerprint:
        raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
    if record.response_body is not None:
        return record, dict(record.response_body)
    return record, None


def _complete_idempotency(record: IdempotencyKey | None, response: dict[str, Any]) -> None:
    if record is None:
        return
    record.response_status = 200
    record.response_body = _json_safe(response)
    record.locked_until = None
    record.save(update_fields=["response_status", "response_body", "locked_until"])


def _manifest_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _fernet() -> Fernet:
    digest = hashlib.sha256(str(settings.BOARDING_OFFLINE_ENCRYPTION_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _package_signature(ciphertext: bytes) -> bytes:
    return hmac.new(
        str(settings.BOARDING_OFFLINE_SIGNING_KEY).encode(),
        ciphertext,
        hashlib.sha256,
    ).digest()


def _get_trip(*, context: OfficeContext, trip_id: str, for_update: bool = False) -> Trip:
    queryset = Trip.objects.filter(public_id=trip_id, office=context.office)
    if for_update:
        queryset = queryset.select_for_update()
    trip = queryset.first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return trip


def _manifest_payload(trip: Trip) -> dict[str, Any]:
    assignments = {
        assignment.passenger_id: assignment
        for assignment in SeatAssignment.objects.select_related("trip_seat").filter(
            trip=trip,
            status=SeatAssignment.Status.ACTIVE,
        )
    }
    tickets = {
        ticket.passenger_id: ticket
        for ticket in Ticket.objects.filter(
            booking__trip=trip, status__in=[Ticket.Status.ACTIVE, Ticket.Status.USED]
        ).order_by("passenger_id", "version_no")
    }
    passengers = (
        BookingPassenger.objects.select_related("booking")
        .filter(
            booking__trip=trip,
            status=BookingPassenger.Status.ACTIVE,
            booking__status__in=[Booking.Status.CONFIRMED, Booking.Status.DENIED_BOARDING_REVIEW],
        )
        .order_by("booking__pnr", "sequence_no")
    )
    rows: list[dict[str, Any]] = []
    for passenger in passengers:
        assignment = assignments.get(passenger.id)
        ticket = tickets.get(passenger.id)
        rows.append(
            {
                "passenger_id": str(passenger.id),
                "pnr": passenger.booking.pnr,
                "full_name": passenger.full_name,
                "identity_tail": (passenger.identity_number_normalized or "")[-4:] or None,
                "seat_code": assignment.trip_seat.seat_code if assignment else None,
                "boarding_status": passenger.boarding_status,
                "ticket_id": str(ticket.id) if ticket else None,
                "ticket_version": ticket.version_no if ticket else None,
                "ticket_status": ticket.status if ticket else None,
            }
        )
    return {
        "trip_id": trip.public_id,
        "trip_version": trip.version,
        "scheduled_departure_at": trip.scheduled_departure_at.isoformat(),
        "status": trip.status,
        "passengers": rows,
    }


@transaction.atomic
def generate_manifest(
    *,
    trip: Trip,
    status: str,
    actor: User | None,
) -> TripManifest:
    locked = Trip.objects.select_for_update().get(id=trip.id)
    payload = _manifest_payload(locked)
    latest = (
        TripManifest.objects.filter(trip=locked).order_by("-version_no").values_list("version_no", flat=True).first()
        or 0
    )
    return TripManifest.objects.create(
        trip=locked,
        version_no=latest + 1,
        status=status,
        manifest_json=payload,
        sha256=_manifest_hash(payload),
        generated_by=actor,
    )


def serialize_manifest(manifest: TripManifest) -> dict[str, Any]:
    actual_hash = _manifest_hash(dict(manifest.manifest_json))
    if not hmac.compare_digest(actual_hash, manifest.sha256):
        raise DomainAPIException("MANIFEST_INTEGRITY_FAILED")
    return {
        "id": str(manifest.id),
        "trip_id": manifest.trip.public_id,
        "version": manifest.version_no,
        "status": manifest.status,
        "sha256": manifest.sha256,
        "generated_at": manifest.generated_at,
        "manifest": manifest.manifest_json,
    }


def get_manifest(*, context: OfficeContext, trip_id: str, version: str | None) -> TripManifest:
    trip = _get_trip(context=context, trip_id=trip_id)
    queryset = TripManifest.objects.filter(trip=trip).select_related("trip")
    if version:
        try:
            version_no = int(version)
        except ValueError as exc:
            raise DomainAPIException("VALIDATION_ERROR") from exc
        manifest = queryset.filter(version_no=version_no).first()
    else:
        manifest = queryset.order_by("-version_no").first()
    if manifest is not None:
        return manifest
    return generate_manifest(trip=trip, status=TripManifest.Status.DRAFT, actor=None)


def _resolve_ticket_or_passenger(
    *,
    trip: Trip,
    data: dict[str, Any],
) -> tuple[BookingPassenger, Ticket | None, bool]:
    qr_data = data.get("ticket_qr")
    manual = not bool(qr_data)
    ticket: Ticket | None = None
    if qr_data:
        verified = verify_ticket_qr(str(qr_data))
        ticket = (
            Ticket.objects.select_for_update()
            .select_related("passenger__booking", "seat_assignment__trip_seat")
            .get(id=verified.id)
        )
        if ticket.status != Ticket.Status.ACTIVE:
            raise DomainAPIException("TICKET_ALREADY_USED")
        passenger = ticket.passenger
    else:
        passenger_id = cast(str, data.get("passenger_id"))
        candidate = (
            BookingPassenger.objects.select_for_update()
            .select_related("booking")
            .filter(id=passenger_id, booking__trip=trip)
            .first()
        )
        if candidate is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        passenger = candidate
        ticket = (
            Ticket.objects.select_for_update()
            .filter(passenger=passenger, status__in=[Ticket.Status.ACTIVE, Ticket.Status.USED])
            .order_by("-version_no")
            .first()
        )
    if passenger.booking.trip_id != trip.id:
        raise DomainAPIException("TICKET_INVALID")
    if passenger.status != BookingPassenger.Status.ACTIVE:
        raise DomainAPIException("TICKET_INVALID")
    return passenger, ticket, manual


def _validate_command(
    *,
    trip: Trip,
    passenger: BookingPassenger,
    ticket: Ticket | None,
    command: str,
    reason_code: str | None,
    correction_approval_id: object | None,
) -> BoardingCorrectionApproval | None:
    now = timezone.now()
    current = passenger.boarding_status
    if command in {"arrive", "verify", "board", "deny"} and trip.status != Trip.Status.BOARDING_OPEN:
        raise DomainAPIException("BOARDING_NOT_OPEN")
    if command == "arrive" and current != BookingPassenger.BoardingStatus.NOT_ARRIVED:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    if command == "verify":
        if current not in {
            BookingPassenger.BoardingStatus.NOT_ARRIVED,
            BookingPassenger.BoardingStatus.ARRIVED,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if passenger.booking.status == Booking.Status.AWAITING_PAYMENT:
            raise DomainAPIException("PAYMENT_REQUIRED")
    if command == "board":
        if passenger.booking.status == Booking.Status.AWAITING_PAYMENT:
            raise DomainAPIException("PAYMENT_REQUIRED")
        if current == BookingPassenger.BoardingStatus.BOARDED:
            raise DomainAPIException("TICKET_ALREADY_USED")
        if current not in {
            BookingPassenger.BoardingStatus.NOT_ARRIVED,
            BookingPassenger.BoardingStatus.ARRIVED,
            BookingPassenger.BoardingStatus.VERIFIED,
            BookingPassenger.BoardingStatus.BOARDED_REVERSED,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if ticket is None:
            raise DomainAPIException("TICKET_INVALID")
    if command == "reverse":
        if passenger.boarding_status != BookingPassenger.BoardingStatus.BOARDED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not reason_code:
            raise DomainAPIException("BOARDING_REASON_REQUIRED")
        if trip.status in {Trip.Status.DEPARTED, Trip.Status.ARRIVED, Trip.Status.COMPLETED}:
            approval_id = cast(str, correction_approval_id)
            approval = (
                BoardingCorrectionApproval.objects.select_for_update()
                .filter(
                    id=approval_id,
                    passenger=passenger,
                    status=BoardingCorrectionApproval.Status.APPROVED,
                    approved_by__is_platform_staff=True,
                )
                .first()
            )
            if approval is None:
                raise DomainAPIException("BOARDING_CORRECTION_APPROVAL_REQUIRED")
            return approval
    if command == "deny":
        if current not in {
            BookingPassenger.BoardingStatus.ARRIVED,
            BookingPassenger.BoardingStatus.VERIFIED,
        }:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        if not reason_code:
            raise DomainAPIException("BOARDING_REASON_REQUIRED")
    if command == "no_show":
        if trip.status != Trip.Status.BOARDING_CLOSED or now < trip.scheduled_departure_at:
            raise DomainAPIException("NO_SHOW_NOT_ALLOWED")
        if current not in {
            BookingPassenger.BoardingStatus.NOT_ARRIVED,
            BookingPassenger.BoardingStatus.ARRIVED,
        }:
            raise DomainAPIException("NO_SHOW_NOT_ALLOWED")
        if current == BookingPassenger.BoardingStatus.ARRIVED and not reason_code:
            raise DomainAPIException("BOARDING_REASON_REQUIRED")
        if (
            current == BookingPassenger.BoardingStatus.DENIED
            or passenger.booking.status == Booking.Status.DENIED_BOARDING_REVIEW
        ):
            raise DomainAPIException("NO_SHOW_NOT_ALLOWED")
        if passenger.boarding_status in {
            BookingPassenger.BoardingStatus.BOARDED,
            BookingPassenger.BoardingStatus.BOARDED_REVERSED,
        }:
            raise DomainAPIException("NO_SHOW_NOT_ALLOWED")
    return None


def _mark_booking_no_show_if_complete(booking: Booking) -> bool:
    if booking.status != Booking.Status.CONFIRMED:
        return False
    has_non_no_show = (
        booking.passengers.filter(status=BookingPassenger.Status.ACTIVE)
        .exclude(boarding_status=BookingPassenger.BoardingStatus.NO_SHOW)
        .exists()
    )
    if has_non_no_show:
        return False
    booking.status = Booking.Status.NO_SHOW
    booking.save(update_fields=["status", "updated_at"])
    return True


@transaction.atomic
def execute_boarding_command(
    *,
    context: OfficeContext,
    actor: User,
    session: UserSession | None,
    request: HttpRequest | None,
    trip_id: str,
    data: dict[str, Any],
    offline_package: OfflineBoardingPackage | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    trip = _get_trip(context=context, trip_id=trip_id, for_update=True)
    idempotency: IdempotencyKey | None = None
    if idempotency_key is not None and offline_package is None:
        idempotency, replay = _begin_idempotency(
            scope_type="office_boarding_command",
            scope_id=trip.id,
            key=idempotency_key,
            payload=data,
        )
        if replay is not None:
            return replay
    passenger, ticket, manual = _resolve_ticket_or_passenger(trip=trip, data=data)
    command = str(data["command"])
    reason_code = str(data.get("reason_code") or "") or None
    if manual and command in {"verify", "board"} and not reason_code:
        raise DomainAPIException("BOARDING_REASON_REQUIRED")
    approval = _validate_command(
        trip=trip,
        passenger=passenger,
        ticket=ticket,
        command=command,
        reason_code=reason_code,
        correction_approval_id=data.get("correction_approval_id"),
    )
    previous = passenger.boarding_status
    passenger.boarding_status = COMMAND_TO_STATUS[command]
    passenger.save(update_fields=["boarding_status"])
    now = _event_time(supplied=data.get("occurred_at"), offline_package=offline_package)
    if command == "board" and ticket is not None:
        ticket.status = Ticket.Status.USED
        ticket.used_at = now
        ticket.save(update_fields=["status", "used_at"])
    elif command == "reverse" and ticket is not None:
        ticket.status = Ticket.Status.ACTIVE
        ticket.used_at = None
        ticket.save(update_fields=["status", "used_at"])
        if approval is not None:
            approval.status = BoardingCorrectionApproval.Status.USED
            approval.used_at = timezone.now()
            approval.save(update_fields=["status", "used_at"])
    elif command == "deny":
        passenger.booking.status = Booking.Status.DENIED_BOARDING_REVIEW
        passenger.booking.save(update_fields=["status", "updated_at"])
        from support.services import open_denied_boarding_case

        open_denied_boarding_case(
            trip=trip,
            passenger=passenger,
            actor=actor,
            reason_code=reason_code or "boarding_denied",
            request=request,
        )
    elif command == "no_show":
        _mark_booking_no_show_if_complete(passenger.booking)

    event_type = BoardingEvent.EventType.MANUAL_CHECK if manual and command == "board" else COMMAND_TO_EVENT[command]
    device = session.device if session and session.device_id else None
    event = BoardingEvent.objects.create(
        trip=trip,
        passenger=passenger,
        ticket=ticket,
        event_type=event_type,
        occurred_at=now,
        actor_user=actor,
        device=device,
        offline_event_id=data.get("offline_event_id"),
        reason_code=reason_code,
        metadata={
            "command": command,
            "previous_status": previous,
            "offline": offline_package is not None,
            "package_hash": offline_package.package_hash if offline_package else None,
        },
    )
    record_audit(
        action=f"office.boarding.{command}",
        object_type="booking_passenger",
        object_id=passenger.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        before={"boarding_status": previous},
        after={"boarding_status": passenger.boarding_status},
        reason_code=reason_code,
        metadata={"event_id": str(event.id), "manual": manual, "offline": offline_package is not None},
    )
    OutboxEvent.objects.create(
        aggregate_type="boarding_event",
        aggregate_id=event.id,
        event_type=f"boarding.{command}",
        payload={
            "trip_id": trip.public_id,
            "passenger_id": str(passenger.id),
            "boarding_status": passenger.boarding_status,
        },
    )
    result = {
        "passenger_id": str(passenger.id),
        "boarding_status": passenger.boarding_status,
        "ticket_status": ticket.status if ticket else None,
    }
    _complete_idempotency(idempotency, result)
    return result


def _event_time(
    *,
    supplied: object,
    offline_package: OfflineBoardingPackage | None,
) -> datetime:
    now = timezone.now()
    if offline_package is None:
        return now
    if supplied is None:
        return now
    if not isinstance(supplied, datetime):
        raise DomainAPIException("OFFLINE_PACKAGE_INVALID")
    earliest = offline_package.created_at - timedelta(minutes=5)
    latest = min(offline_package.expires_at, now + timedelta(minutes=5))
    if supplied < earliest or supplied > latest:
        raise DomainAPIException("OFFLINE_PACKAGE_INVALID")
    return supplied


def _require_recent_mfa(session: UserSession | None) -> UserDevice:
    cutoff = timezone.now() - timedelta(seconds=settings.SENSITIVE_MFA_MAX_AGE_SECONDS)
    if session is None or session.mfa_verified_at is None or session.mfa_verified_at < cutoff:
        raise DomainAPIException("AUTH_MFA_REQUIRED")
    if session.device is None or session.device.revoked_at is not None or session.device.trusted_at is None:
        raise DomainAPIException("DEVICE_NOT_TRUSTED")
    return session.device


@transaction.atomic
def create_offline_package(
    *,
    context: OfficeContext,
    actor: User,
    session: UserSession | None,
    request: HttpRequest,
    trip_id: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    trip = _get_trip(context=context, trip_id=trip_id, for_update=True)
    if trip.status != Trip.Status.BOARDING_OPEN:
        raise DomainAPIException("BOARDING_NOT_OPEN")
    device = _require_recent_mfa(session)
    idempotency: IdempotencyKey | None = None
    if idempotency_key is not None:
        idempotency, replay = _begin_idempotency(
            scope_type="offline_boarding_package",
            scope_id=trip.id,
            key=idempotency_key,
            payload={"trip_version": trip.version, "device_id": str(device.id)},
        )
        if replay is not None:
            existing_id = replay.get("package_id")
            existing = (
                OfflineBoardingPackage.objects.filter(id=existing_id).first() if isinstance(existing_id, str) else None
            )
            if existing is None:
                raise DomainAPIException("CONFLICT", details={"reason": "idempotency_result_missing"})
            return _offline_package_response(existing)
    manifest = generate_manifest(trip=trip, status=TripManifest.Status.DRAFT, actor=actor)
    expires_at = timezone.now() + timedelta(seconds=settings.OFFLINE_BOARDING_PACKAGE_TTL_SECONDS)
    payload = {
        "trip_id": trip.public_id,
        "trip_version": trip.version,
        "manifest_version": manifest.version_no,
        "manifest_hash": manifest.sha256,
        "manifest": manifest.manifest_json,
        "device_id": str(device.id),
        "expires_at": expires_at.isoformat(),
    }
    ciphertext = _fernet().encrypt(_canonical(payload))
    package_hash = hashlib.sha256(ciphertext).hexdigest()
    signature = _package_signature(ciphertext)
    package = OfflineBoardingPackage.objects.create(
        trip=trip,
        manifest=manifest,
        device=device,
        trip_version=trip.version,
        package_hash=package_hash,
        ciphertext=ciphertext,
        signature=signature,
        expires_at=expires_at,
        created_by=actor,
    )
    record_audit(
        action="office.boarding.offline_package.create",
        object_type="offline_boarding_package",
        object_id=package.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        metadata={"trip_id": trip.public_id, "device_id": str(device.id), "manifest_hash": manifest.sha256},
    )
    _complete_idempotency(idempotency, {"package_id": str(package.id)})
    return _offline_package_response(package)


def _offline_package_response(package: OfflineBoardingPackage) -> dict[str, Any]:
    data_url = "data:application/octet-stream;base64," + base64.b64encode(bytes(package.ciphertext)).decode()
    return {
        "download_url": data_url,
        "expires_at": package.expires_at,
        "package_hash": package.package_hash,
    }


def _record_conflict(
    *,
    package: OfflineBoardingPackage,
    event: dict[str, Any],
    conflict_type: str,
    passenger: BookingPassenger | None = None,
    ticket: Ticket | None = None,
) -> dict[str, Any]:
    conflict, _ = BoardingSyncConflict.objects.get_or_create(
        package=package,
        offline_event_id=str(event.get("offline_event_id") or "missing"),
        defaults={
            "passenger": passenger,
            "ticket": ticket,
            "conflict_type": conflict_type,
            "event_payload": event,
        },
    )
    return {
        "offline_event_id": conflict.offline_event_id,
        "type": conflict.conflict_type,
        "conflict_id": str(conflict.id),
    }


@transaction.atomic
def sync_offline_events(
    *,
    context: OfficeContext,
    actor: User,
    session: UserSession | None,
    request: HttpRequest,
    trip_id: str,
    package_hash: str,
    events: list[dict[str, Any]],
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    trip = _get_trip(context=context, trip_id=trip_id, for_update=True)
    device = _require_recent_mfa(session)
    package = (
        OfflineBoardingPackage.objects.select_for_update()
        .filter(package_hash=package_hash, trip=trip, device=device)
        .first()
    )
    if package is None:
        raise DomainAPIException("OFFLINE_PACKAGE_INVALID")
    if package.expires_at <= timezone.now():
        raise DomainAPIException("OFFLINE_PACKAGE_EXPIRED")
    if not hmac.compare_digest(bytes(package.signature), _package_signature(bytes(package.ciphertext))):
        raise DomainAPIException("OFFLINE_PACKAGE_INVALID")

    idempotency: IdempotencyKey | None = None
    if idempotency_key is not None:
        idempotency, replay = _begin_idempotency(
            scope_type="offline_boarding_sync",
            scope_id=package.id,
            key=idempotency_key,
            payload={"package_hash": package_hash, "events": events},
        )
        if replay is not None:
            return replay

    accepted = 0
    duplicates = 0
    conflicts: list[dict[str, Any]] = []
    for event in events:
        offline_event_id = str(event.get("offline_event_id") or "").strip()
        if not offline_event_id:
            conflicts.append(_record_conflict(package=package, event=event, conflict_type="offline_event_id_required"))
            continue
        if BoardingEvent.objects.filter(device=device, offline_event_id=offline_event_id).exists():
            duplicates += 1
            continue
        if package.trip_version != trip.version:
            conflicts.append(_record_conflict(package=package, event=event, conflict_type="trip_revision_mismatch"))
            continue
        if event.get("command") not in {"arrive", "verify", "board"}:
            conflicts.append(
                _record_conflict(package=package, event=event, conflict_type="offline_command_not_allowed")
            )
            continue
        try:
            execute_boarding_command(
                context=context,
                actor=actor,
                session=session,
                request=request,
                trip_id=trip_id,
                data=event,
                offline_package=package,
            )
            accepted += 1
        except (DomainAPIException, IntegrityError) as exc:
            code = getattr(exc, "code", None) or "offline_sync_conflict"
            conflicts.append(_record_conflict(package=package, event=event, conflict_type=str(code)))
    package.synced_at = timezone.now()
    package.save(update_fields=["synced_at"])
    record_audit(
        action="office.boarding.offline_sync",
        object_type="offline_boarding_package",
        object_id=package.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        metadata={"accepted": accepted, "duplicates": duplicates, "conflicts": len(conflicts)},
    )
    result = {"accepted": accepted, "duplicates": duplicates, "conflicts": conflicts, "purge_required": True}
    _complete_idempotency(idempotency, result)
    return result


@transaction.atomic
def mark_due_no_shows() -> int:
    now = timezone.now()
    trips = Trip.objects.filter(status=Trip.Status.BOARDING_CLOSED, scheduled_departure_at__lte=now)
    changed = 0
    for trip in trips:
        passengers = BookingPassenger.objects.select_for_update().filter(
            booking__trip=trip,
            booking__status=Booking.Status.CONFIRMED,
            status=BookingPassenger.Status.ACTIVE,
            boarding_status=BookingPassenger.BoardingStatus.NOT_ARRIVED,
        )
        for passenger in passengers:
            passenger.boarding_status = BookingPassenger.BoardingStatus.NO_SHOW
            passenger.save(update_fields=["boarding_status"])
            event = BoardingEvent.objects.create(
                trip=trip,
                passenger=passenger,
                event_type=BoardingEvent.EventType.NO_SHOW,
                occurred_at=now,
                reason_code="automatic_after_boarding_close",
                metadata={"automatic": True},
            )
            record_audit(
                action="system.boarding.no_show",
                object_type="booking_passenger",
                object_id=passenger.id,
                actor_type="system",
                office_id=trip.office_id,
                before={"boarding_status": BookingPassenger.BoardingStatus.NOT_ARRIVED},
                after={"boarding_status": BookingPassenger.BoardingStatus.NO_SHOW},
                reason_code="automatic_after_boarding_close",
                metadata={"event_id": str(event.id), "trip_id": trip.public_id},
            )
            OutboxEvent.objects.create(
                aggregate_type="boarding_event",
                aggregate_id=event.id,
                event_type="boarding.no_show",
                payload={
                    "trip_id": trip.public_id,
                    "passenger_id": str(passenger.id),
                    "automatic": True,
                },
            )
            if _mark_booking_no_show_if_complete(passenger.booking):
                OutboxEvent.objects.create(
                    aggregate_type="booking",
                    aggregate_id=passenger.booking.id,
                    event_type="booking.no_show",
                    payload={"trip_id": trip.public_id, "pnr": passenger.booking.pnr},
                )
            changed += 1
    return changed
