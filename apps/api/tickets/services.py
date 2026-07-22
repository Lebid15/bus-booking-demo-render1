from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking, BookingPassenger, SeatAssignment
from common.exceptions import DomainAPIException
from common.models import OutboxEvent
from tickets.models import Ticket


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: bytes) -> bytes:
    key = str(settings.TICKET_QR_SIGNING_KEY).encode()
    return hmac.new(key, payload, hashlib.sha256).digest()


def ticket_qr_data(ticket: Ticket) -> str:
    payload = json.dumps(
        {"ticket_id": str(ticket.id), "version": ticket.version_no},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = _sign(payload)
    return f"tq1.{_b64encode(payload)}.{_b64encode(signature)}"


def ticket_qr_hash(qr_data: str) -> bytes:
    return hashlib.sha256(qr_data.encode()).digest()


def verify_ticket_qr(qr_data: str) -> Ticket:
    try:
        prefix, payload_encoded, signature_encoded = qr_data.split(".", 2)
        if prefix != "tq1":
            raise ValueError
        payload = _b64decode(payload_encoded)
        signature = _b64decode(signature_encoded)
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError
        decoded = json.loads(payload.decode())
        ticket_id = decoded["ticket_id"]
        version = int(decoded["version"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise DomainAPIException("TICKET_QR_INVALID") from exc

    ticket = Ticket.objects.select_related("passenger", "seat_assignment").filter(
        id=ticket_id,
        version_no=version,
    ).first()
    if ticket is None:
        raise DomainAPIException("TICKET_QR_INVALID")
    if not hmac.compare_digest(bytes(ticket.qr_token_hash), ticket_qr_hash(qr_data)):
        raise DomainAPIException("TICKET_QR_INVALID")
    if not hmac.compare_digest(bytes(ticket.qr_payload_signature), signature):
        raise DomainAPIException("TICKET_QR_INVALID")
    if ticket.status == Ticket.Status.USED:
        raise DomainAPIException("TICKET_ALREADY_USED")
    if ticket.status != Ticket.Status.ACTIVE:
        raise DomainAPIException("TICKET_QR_REVOKED")
    return ticket


def serialize_ticket(ticket: Ticket) -> dict[str, Any]:
    return {
        "id": str(ticket.id),
        "version": ticket.version_no,
        "status": ticket.status,
        "qr_data": ticket_qr_data(ticket),
        "seat_code": ticket.seat_assignment.trip_seat.seat_code,
        "pdf_url": (
            f"/v1/public/bookings/{ticket.booking.pnr}/tickets/{ticket.id}/document"
        ),
    }


@transaction.atomic
def issue_tickets_for_booking(booking: Booking) -> list[Ticket]:
    locked_booking = Booking.objects.select_for_update().get(id=booking.id)
    if locked_booking.status != Booking.Status.CONFIRMED:
        return []

    passengers = list(
        BookingPassenger.objects.select_for_update()
        .filter(booking=locked_booking)
        .order_by("sequence_no")
    )
    assignments = {
        assignment.passenger_id: assignment
        for assignment in SeatAssignment.objects.select_for_update()
        .select_related("trip_seat")
        .filter(booking=locked_booking, status=SeatAssignment.Status.ACTIVE)
    }
    issued: list[Ticket] = []
    for passenger in passengers:
        existing = (
            Ticket.objects.select_for_update()
            .select_related("seat_assignment__trip_seat")
            .filter(passenger=passenger, status=Ticket.Status.ACTIVE)
            .first()
        )
        assignment = assignments.get(passenger.id)
        if assignment is None:
            raise DomainAPIException("TRIP_INVENTORY_INVALID")
        if existing is not None:
            issued.append(existing)
            continue
        latest_version = (
            Ticket.objects.filter(passenger=passenger)
            .order_by("-version_no")
            .values_list("version_no", flat=True)
            .first()
            or 0
        )
        ticket = Ticket(
            booking=locked_booking,
            passenger=passenger,
            seat_assignment=assignment,
            version_no=latest_version + 1,
            qr_token_hash=b"",
            qr_payload_signature=b"",
        )
        qr_data = ticket_qr_data(ticket)
        ticket.qr_token_hash = ticket_qr_hash(qr_data)
        payload_encoded = qr_data.split(".", 2)[1]
        ticket.qr_payload_signature = _sign(_b64decode(payload_encoded))
        ticket.save(force_insert=True)
        issued.append(ticket)
        OutboxEvent.objects.create(
            aggregate_type="ticket",
            aggregate_id=ticket.id,
            event_type="ticket.issued",
            payload={
                "ticket_id": str(ticket.id),
                "booking_id": locked_booking.public_id,
                "passenger_id": str(passenger.id),
                "version": ticket.version_no,
            },
        )
    return issued


@transaction.atomic
def reissue_ticket_for_passenger(
    *,
    passenger: BookingPassenger,
    seat_assignment: SeatAssignment,
    reason: str,
) -> Ticket:
    now = timezone.now()
    active = list(
        Ticket.objects.select_for_update().filter(
            passenger=passenger,
            status=Ticket.Status.ACTIVE,
        )
    )
    for ticket in active:
        ticket.status = Ticket.Status.REVOKED
        ticket.revoked_at = now
        ticket.save(update_fields=["status", "revoked_at"])
        OutboxEvent.objects.create(
            aggregate_type="ticket",
            aggregate_id=ticket.id,
            event_type="ticket.revoked",
            payload={"ticket_id": str(ticket.id), "reason": reason},
        )
    latest_version = (
        Ticket.objects.filter(passenger=passenger)
        .order_by("-version_no")
        .values_list("version_no", flat=True)
        .first()
        or 0
    )
    replacement = Ticket(
        booking=passenger.booking,
        passenger=passenger,
        seat_assignment=seat_assignment,
        version_no=latest_version + 1,
        qr_token_hash=b"",
        qr_payload_signature=b"",
    )
    qr_data = ticket_qr_data(replacement)
    replacement.qr_token_hash = ticket_qr_hash(qr_data)
    replacement.qr_payload_signature = _sign(_b64decode(qr_data.split(".", 2)[1]))
    replacement.save(force_insert=True)
    OutboxEvent.objects.create(
        aggregate_type="ticket",
        aggregate_id=replacement.id,
        event_type="ticket.reissued",
        payload={
            "ticket_id": str(replacement.id),
            "booking_id": passenger.booking.public_id,
            "passenger_id": str(passenger.id),
            "version": replacement.version_no,
            "reason": reason,
        },
    )
    return replacement


@transaction.atomic
def revoke_tickets_for_passenger(*, passenger: BookingPassenger, reason: str) -> int:
    now = timezone.now()
    tickets = list(
        Ticket.objects.select_for_update().filter(
            passenger=passenger,
            status=Ticket.Status.ACTIVE,
        )
    )
    for ticket in tickets:
        ticket.status = Ticket.Status.REVOKED
        ticket.revoked_at = now
        ticket.save(update_fields=["status", "revoked_at"])
        OutboxEvent.objects.create(
            aggregate_type="ticket",
            aggregate_id=ticket.id,
            event_type="ticket.revoked",
            payload={"ticket_id": str(ticket.id), "reason": reason},
        )
    return len(tickets)
