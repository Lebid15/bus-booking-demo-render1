from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingPassenger, SeatAssignment
from bookings.services import manage_token_matches
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from identity.models import User
from organizations.services import OfficeContext
from support.models import OfficeViolation, SupportCase, SupportMessage
from tickets.models import Ticket
from trips.models import Trip, TripOperationalIssue

OPEN_SUPPORT_STATUSES = {
    SupportCase.Status.OPEN,
    SupportCase.Status.ASSIGNED,
    SupportCase.Status.AWAITING_CUSTOMER,
    SupportCase.Status.AWAITING_OFFICE,
    SupportCase.Status.ESCALATED,
    SupportCase.Status.REOPENED,
}


def _sla_minutes(priority: str) -> int:
    defaults = {"P0": 5, "P1": 15, "P2": 60, "P3": 240, "P4": 1440}
    override = getattr(settings, f"SUPPORT_{priority}_SLA_MINUTES", None)
    return int(override if override is not None else defaults.get(priority, 240))


def serialize_case(case: SupportCase) -> dict[str, Any]:
    return {
        "id": case.public_id,
        "priority": case.priority,
        "category": case.category,
        "status": case.status,
        "booking_id": case.booking.public_id if case.booking_id and case.booking is not None else None,
        "trip_id": case.trip.public_id if case.trip_id and case.trip is not None else None,
        "office_id": case.office.public_id if case.office_id and case.office is not None else None,
        "sla_due_at": case.sla_due_at,
        "opened_at": case.opened_at,
        "resolution_code": case.resolution_code,
        "metadata": case.metadata,
    }


@transaction.atomic
def open_guest_support_case(
    *,
    pnr: str,
    manage_token: str,
    data: dict[str, Any],
    request: HttpRequest | None,
    idempotency_key: str,
) -> SupportCase:
    booking = (
        Booking.objects.select_for_update().select_related("trip", "office").filter(pnr=pnr.strip().upper()).first()
    )
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    record, replay = begin_idempotency(
        scope_type="guest_support_case",
        scope_id=booking.id,
        key=idempotency_key,
        payload=data,
    )
    if replay is not None:
        return SupportCase.objects.get(id=replay["case_id"])
    priority = str(data["priority"])
    now = timezone.now()
    case = SupportCase.objects.create(
        booking=booking,
        trip=booking.trip,
        office=booking.office,
        priority=priority,
        category=str(data["category"]),
        status=SupportCase.Status.AWAITING_OFFICE,
        sla_due_at=now + timedelta(minutes=_sla_minutes(priority)),
        metadata={"attachments": list(data.get("attachments", [])), "source": "guest"},
    )
    SupportMessage.objects.create(
        case=case,
        sender_type=SupportMessage.SenderType.CUSTOMER,
        body=str(data["message"]),
    )
    OutboxEvent.objects.create(
        aggregate_type="support_case",
        aggregate_id=case.id,
        event_type="support.case.opened",
        payload={"case_id": case.public_id, "priority": priority, "office_id": booking.office.public_id},
    )
    complete_idempotency(record, {"case_id": str(case.id)})
    record_audit(
        action="public.support_case.open",
        object_type="support_case",
        object_id=case.id,
        actor_type="guest",
        office_id=booking.office_id,
        request=request,
        after={"priority": priority, "category": case.category, "status": case.status},
    )
    return case


@transaction.atomic
def open_denied_boarding_case(
    *,
    trip: Trip,
    passenger: BookingPassenger,
    actor: User,
    reason_code: str,
    request: HttpRequest | None,
) -> SupportCase:
    existing = (
        SupportCase.objects.select_for_update()
        .filter(
            booking=passenger.booking,
            trip=trip,
            category="boarding_denial_valid_ticket",
            status__in=OPEN_SUPPORT_STATUSES,
        )
        .first()
    )
    if existing is not None:
        return existing
    now = timezone.now()
    case = SupportCase.objects.create(
        booking=passenger.booking,
        trip=trip,
        office=trip.office,
        opened_by_user=actor,
        priority=SupportCase.Priority.P1,
        category="boarding_denial_valid_ticket",
        status=SupportCase.Status.ESCALATED,
        sla_due_at=now + timedelta(minutes=_sla_minutes("P1")),
        metadata={"passenger_id": str(passenger.id), "reason_code": reason_code, "auto_escalated": True},
    )
    SupportMessage.objects.create(
        case=case,
        sender_type=SupportMessage.SenderType.SYSTEM,
        body="تم فتح حالة P1 تلقائيًا بسبب رفض تذكرة صحيحة أثناء الصعود.",
    )
    assignment = (
        SeatAssignment.objects.select_for_update()
        .filter(passenger=passenger, status=SeatAssignment.Status.ACTIVE)
        .select_related("trip_seat")
        .first()
    )
    if assignment is not None:
        assignment.trip_seat.sellable = False
        assignment.trip_seat.blocked_reason = f"support_case:{case.public_id}"
        assignment.trip_seat.save(update_fields=["sellable", "blocked_reason"])
    OutboxEvent.objects.create(
        aggregate_type="support_case",
        aggregate_id=case.id,
        event_type="support.p1.auto_escalated",
        payload={"case_id": case.public_id, "trip_id": trip.public_id, "booking_id": passenger.booking.public_id},
    )
    record_audit(
        action="system.support_case.boarding_denial_open",
        object_type="support_case",
        object_id=case.id,
        actor_user=actor,
        actor_type="system",
        office_id=trip.office_id,
        request=request,
        after={"priority": "P1", "status": case.status, "seat_frozen": assignment is not None},
        reason_code=reason_code,
    )
    return case


@transaction.atomic
def add_support_message(
    *,
    case: SupportCase,
    actor: User,
    sender_type: str,
    body: str,
    visibility: str,
    request: HttpRequest | None,
    idempotency_key: str,
) -> SupportMessage:
    locked = SupportCase.objects.select_for_update().get(id=case.id)
    record, replay = begin_idempotency(
        scope_type="support_message",
        scope_id=locked.id,
        key=idempotency_key,
        payload={"sender_type": sender_type, "body": body, "visibility": visibility},
    )
    if replay is not None:
        return SupportMessage.objects.get(id=replay["message_id"])
    if locked.status not in OPEN_SUPPORT_STATUSES:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    message = SupportMessage.objects.create(
        case=locked,
        sender_type=sender_type,
        sender_user=actor,
        body=body,
        visibility=visibility,
    )
    if sender_type == SupportMessage.SenderType.OFFICE:
        locked.status = SupportCase.Status.AWAITING_CUSTOMER
    elif sender_type == SupportMessage.SenderType.PLATFORM:
        locked.status = SupportCase.Status.ASSIGNED
        locked.owner_user = actor
    locked.save(update_fields=["status", "owner_user"])
    complete_idempotency(record, {"message_id": str(message.id)})
    record_audit(
        action=f"{sender_type}.support_case.reply",
        object_type="support_case",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        after={"message_id": str(message.id), "status": locked.status, "visibility": visibility},
    )
    return message


@transaction.atomic
def command_support_case(
    *,
    case: SupportCase,
    actor: User,
    command: str,
    resolution_code: str | None,
    request: HttpRequest | None,
    idempotency_key: str,
) -> SupportCase:
    locked = SupportCase.objects.select_for_update().get(id=case.id)
    record, replay = begin_idempotency(
        scope_type="support_case_command",
        scope_id=locked.id,
        key=idempotency_key,
        payload={"command": command, "resolution_code": resolution_code},
    )
    if replay is not None:
        return SupportCase.objects.get(id=replay["case_id"])
    now = timezone.now()
    before = locked.status
    if command == "assign":
        locked.owner_user = actor
        locked.status = SupportCase.Status.ASSIGNED
    elif command == "resolve":
        if not resolution_code:
            raise DomainAPIException("VALIDATION_ERROR", details=[{"field": "resolution_code", "reason": "required"}])
        locked.status = SupportCase.Status.RESOLVED
        locked.resolution_code = resolution_code
        locked.resolved_at = now
        TripOperationalIssue.objects.filter(
            trip=locked.trip,
            status=TripOperationalIssue.Status.OPEN,
            details__support_case_id=locked.public_id,
        ).update(status=TripOperationalIssue.Status.RESOLVED, resolved_at=now)
    elif command == "close":
        if locked.status != SupportCase.Status.RESOLVED:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        locked.status = SupportCase.Status.CLOSED
        locked.closed_at = now
    elif command == "reopen":
        if locked.status not in {SupportCase.Status.RESOLVED, SupportCase.Status.CLOSED}:
            raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
        locked.status = SupportCase.Status.REOPENED
        locked.resolved_at = None
        locked.closed_at = None
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    locked.save()
    complete_idempotency(record, {"case_id": str(locked.id)})
    record_audit(
        action=f"platform.support_case.{command}",
        object_type="support_case",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        before={"status": before},
        after={"status": locked.status, "resolution_code": locked.resolution_code},
    )
    return locked


@transaction.atomic
def escalate_overdue_support_cases(*, now=None) -> int:  # type: ignore[no-untyped-def]
    current = now or timezone.now()
    due_ids = list(
        SupportCase.objects.filter(
            status=SupportCase.Status.AWAITING_OFFICE,
            sla_due_at__isnull=False,
            sla_due_at__lte=current,
        ).values_list("id", flat=True)
    )
    escalated = 0
    for case_id in due_ids:
        case = SupportCase.objects.select_for_update(of=("self",)).select_related("office").filter(id=case_id).first()
        if case is None or case.status != SupportCase.Status.AWAITING_OFFICE:
            continue
        office_replied = case.messages.filter(sender_type=SupportMessage.SenderType.OFFICE).exists()
        if office_replied:
            continue
        case.status = SupportCase.Status.ESCALATED
        case.save(update_fields=["status"])
        OfficeViolation.objects.get_or_create(
            support_case=case,
            code="SUPPORT_SLA_BREACH",
            defaults={
                "office": case.office,
                "severity": case.priority,
                "details": {"sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None},
            },
        )
        SupportMessage.objects.create(
            case=case,
            sender_type=SupportMessage.SenderType.SYSTEM,
            visibility=SupportMessage.Visibility.INTERNAL,
            body="انتهت مهلة رد المكتب؛ تم تحويل الحالة تلقائيًا إلى المنصة وتسجيل مخالفة.",
        )
        OutboxEvent.objects.create(
            aggregate_type="support_case",
            aggregate_id=case.id,
            event_type="support.case.sla_escalated",
            payload={
                "case_id": case.public_id,
                "office_id": case.office.public_id if case.office is not None else None,
            },
        )
        record_audit(
            action="system.support_case.sla_escalate",
            object_type="support_case",
            object_id=case.id,
            actor_type="system",
            office_id=case.office_id,
            after={"status": case.status, "violation_code": "SUPPORT_SLA_BREACH"},
        )
        escalated += 1
    return escalated


def recovery_lookup(*, context: OfficeContext, trip_id: str, pnr: str, identity_tail: str | None) -> dict[str, Any]:
    trip = Trip.objects.filter(public_id=trip_id, office=context.office).first()
    if trip is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    booking = Booking.objects.filter(trip=trip, pnr=pnr.strip().upper()).first()
    if booking is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    passengers = BookingPassenger.objects.filter(booking=booking, status=BookingPassenger.Status.ACTIVE).order_by(
        "sequence_no"
    )
    if identity_tail:
        passengers = passengers.filter(identity_number_normalized__endswith=identity_tail.strip())
    rows: list[dict[str, Any]] = []
    for passenger in passengers:
        assignment = (
            SeatAssignment.objects.filter(passenger=passenger, status=SeatAssignment.Status.ACTIVE)
            .select_related("trip_seat")
            .first()
        )
        ticket = Ticket.objects.filter(passenger=passenger).order_by("-version_no").first()
        rows.append(
            {
                "passenger_id": str(passenger.id),
                "full_name": passenger.full_name,
                "identity_tail": (passenger.identity_number_normalized or "")[-4:] or None,
                "seat_code": assignment.trip_seat.seat_code if assignment else None,
                "boarding_status": passenger.boarding_status,
                "ticket_status": ticket.status if ticket else None,
            }
        )
    if not rows:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    return {
        "pnr": booking.pnr,
        "booking_status": booking.status,
        "payment_status": booking.payment_status,
        "payment_required": False,
        "verification_source": "manifest_pnr_recovery",
        "passengers": rows,
    }
