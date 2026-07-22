from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking, BookingPassenger
from common.exceptions import DomainAPIException
from common.models import IdempotencyKey, OutboxEvent
from finance.services import money, post_refund_approved_entry, post_refund_succeeded_entry
from identity.models import User
from organizations.services import OfficeContext, require_fresh_mfa
from payments.models import Chargeback, PaymentIntent, Refund

OPEN_REFUND_STATUSES = {
    Refund.Status.REQUESTED,
    Refund.Status.UNDER_REVIEW,
    Refund.Status.APPROVED,
    Refund.Status.PROCESSING,
}
OPEN_CHARGEBACK_STATUSES = {
    Chargeback.Status.OPEN,
    Chargeback.Status.EVIDENCE_SUBMITTED,
    Chargeback.Status.ACCEPTED,
}


def serialize_refund(refund: Refund) -> dict[str, Any]:
    passenger_name = refund.passenger.full_name if refund.passenger is not None else None
    return {
        "id": str(refund.id),
        "booking_id": refund.booking.public_id,
        "pnr": refund.booking.pnr,
        "passenger_id": str(refund.passenger_id) if refund.passenger_id else None,
        "passenger_name": passenger_name,
        "status": refund.status,
        "requested_amount": str(refund.requested_amount),
        "approved_amount": str(refund.approved_amount) if refund.approved_amount is not None else None,
        "currency": refund.currency,
        "reason_code": refund.reason_code,
        "provider_reference": refund.provider_reference,
        "requested_by": str(refund.requested_by_id) if refund.requested_by_id else None,
        "approved_by": str(refund.approved_by_id) if refund.approved_by_id else None,
        "created_at": refund.created_at,
        "completed_at": refund.completed_at,
    }


def _queryset() -> models.QuerySet[Refund]:
    return Refund.objects.select_related("booking", "booking__office", "passenger", "payment_intent")


def list_office_refunds(*, context: OfficeContext, status_filter: str | None = None) -> list[dict[str, Any]]:
    queryset = _queryset().filter(booking__office=context.office).order_by("-created_at")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return [serialize_refund(refund) for refund in queryset]


def list_platform_refunds(*, status_filter: str | None = None, office_id: str | None = None) -> list[dict[str, Any]]:
    queryset = _queryset().order_by("-created_at")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if office_id:
        queryset = queryset.filter(booking__office__public_id=office_id)
    return [serialize_refund(refund) for refund in queryset]


def list_chargebacks(*, status_filter: str | None = None) -> list[dict[str, Any]]:
    queryset = Chargeback.objects.select_related(
        "payment_transaction__payment_intent__booking"
    ).order_by("-opened_at")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    return [
        {
            "id": str(item.id),
            "provider_case_id": item.provider_case_id,
            "status": item.status,
            "amount": str(item.amount),
            "currency": item.currency,
            "booking_id": item.payment_transaction.payment_intent.booking.public_id,
            "opened_at": item.opened_at,
            "deadline_at": item.deadline_at,
        }
        for item in queryset
    ]


def _fingerprint(command: str, data: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({"command": command, **data}, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _has_open_chargeback(refund: Refund) -> bool:
    return Chargeback.objects.filter(
        payment_transaction__payment_intent__booking=refund.booking,
        status__in=OPEN_CHARGEBACK_STATUSES,
        currency=refund.currency,
    ).exists()


def _available_refund_amount(refund: Refund) -> Decimal:
    booking = refund.booking
    other_reserved = money(
        sum(
            Refund.objects.filter(
                booking=booking,
                status__in=[*OPEN_REFUND_STATUSES, Refund.Status.SUCCEEDED],
            )
            .exclude(id=refund.id)
            .values_list("requested_amount", flat=True),
            Decimal("0.00"),
        )
    )
    chargeback_reserved = money(
        sum(
            Chargeback.objects.filter(
                payment_transaction__payment_intent__booking=booking,
                status__in=OPEN_CHARGEBACK_STATUSES,
                currency=booking.currency,
            ).values_list("amount", flat=True),
            Decimal("0.00"),
        )
    )
    return money(max(Decimal("0.00"), booking.paid_amount - other_reserved - chargeback_reserved))


def _finalize_booking_after_refund(refund: Refund) -> None:
    booking = Booking.objects.select_for_update().get(id=refund.booking_id)
    amount = money(refund.approved_amount or refund.requested_amount)
    booking.refunded_amount = money(booking.refunded_amount + amount)
    if booking.refunded_amount >= booking.paid_amount and booking.paid_amount > 0:
        booking.payment_status = Booking.PaymentStatus.REFUNDED
    else:
        booking.payment_status = Booking.PaymentStatus.PARTIALLY_REFUNDED
    has_active_passengers = BookingPassenger.objects.filter(
        booking=booking,
        status=BookingPassenger.Status.ACTIVE,
    ).exists()
    has_open_refunds = Refund.objects.filter(booking=booking, status__in=OPEN_REFUND_STATUSES).exclude(
        id=refund.id
    ).exists()
    if not has_active_passengers and not has_open_refunds:
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
    booking.save(
        update_fields=["refunded_amount", "payment_status", "status", "cancelled_at", "updated_at"]
    )


def _assert_state(refund: Refund, allowed: set[str]) -> None:
    if refund.status not in allowed:
        raise DomainAPIException("REFUND_STATE_CONFLICT")


@transaction.atomic
def command_refund(
    *,
    refund_id: uuid.UUID,
    command: str,
    actor: User,
    request: HttpRequest,
    idempotency_key: str,
    data: dict[str, Any],
    context: OfficeContext | None = None,
    platform: bool = False,
) -> dict[str, Any]:
    refund = _queryset().select_for_update(of=("self",)).filter(id=refund_id).first()
    if refund is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if context is not None and refund.booking.office_id != context.office.id:
        raise DomainAPIException("TENANT_ACCESS_DENIED")
    if not platform and context is None:
        raise DomainAPIException("PERMISSION_DENIED")

    fingerprint = _fingerprint(command, data)
    replay = IdempotencyKey.objects.select_for_update().filter(
        scope_type="refund_command", scope_id=refund.id, key=idempotency_key
    ).first()
    if replay is not None:
        if replay.request_hash != fingerprint:
            raise DomainAPIException("CONFLICT", details={"reason": "idempotency_key_reused"})
        return serialize_refund(refund)
    IdempotencyKey.objects.create(
        scope_type="refund_command",
        scope_id=refund.id,
        key=idempotency_key,
        request_hash=fingerprint,
        expires_at=timezone.now() + timedelta(days=7),
    )

    before = {"status": refund.status, "approved_amount": str(refund.approved_amount)}
    now = timezone.now()
    if command == "review":
        _assert_state(refund, {Refund.Status.REQUESTED})
        refund.status = Refund.Status.UNDER_REVIEW
    elif command == "approve":
        _assert_state(refund, {Refund.Status.UNDER_REVIEW})
        if refund.requested_by_id is not None and refund.requested_by_id == actor.id:
            raise DomainAPIException("DUAL_APPROVAL_REQUIRED")
        amount = money(data.get("approved_amount", refund.requested_amount))
        if _has_open_chargeback(refund):
            raise DomainAPIException("CHARGEBACK_OPEN")
        if amount <= 0 or amount > refund.requested_amount or amount > _available_refund_amount(refund):
            raise DomainAPIException("REFUND_AMOUNT_EXCEEDS_AVAILABLE")
        if amount >= money(settings.REFUND_DUAL_APPROVAL_THRESHOLD):
            require_fresh_mfa(request)
        refund.approved_amount = amount
        refund.approved_by = actor
        refund.status = Refund.Status.APPROVED
        post_refund_approved_entry(
            refund_id=refund.id,
            booking=refund.booking,
            amount=amount,
            occurred_at=now,
        )
    elif command == "reject":
        _assert_state(refund, {Refund.Status.UNDER_REVIEW})
        reason = str(data.get("reason") or "").strip()
        if not reason:
            raise DomainAPIException("REFUND_REJECTION_REASON_REQUIRED")
        refund.rejection_reason = reason
        refund.status = Refund.Status.REJECTED
        refund.completed_at = now
    elif command == "process":
        _assert_state(refund, {Refund.Status.APPROVED})
        refund.status = Refund.Status.PROCESSING
        OutboxEvent.objects.create(
            aggregate_type="refund",
            aggregate_id=refund.id,
            event_type="refund.processing_requested",
            payload={
                "refund_id": str(refund.id),
                "booking_id": refund.booking.public_id,
                "amount": str(refund.approved_amount),
                "currency": refund.currency,
                "payment_intent_id": refund.payment_intent.public_id if refund.payment_intent else None,
            },
        )
    elif command == "succeed":
        _assert_state(refund, {Refund.Status.PROCESSING})
        reference = str(data.get("provider_reference") or "").strip()
        if not reference:
            raise DomainAPIException("REFUND_CONFIRMATION_INVALID")
        refund.provider_reference = reference
        refund.status = Refund.Status.SUCCEEDED
        refund.completed_at = now
        amount = money(refund.approved_amount or refund.requested_amount)
        electronic = bool(
            refund.payment_intent
            and refund.payment_intent.method_type == PaymentIntent.MethodType.ELECTRONIC
        )
        post_refund_succeeded_entry(
            refund_id=refund.id,
            booking=refund.booking,
            amount=amount,
            occurred_at=now,
            electronic=electronic,
        )
        _finalize_booking_after_refund(refund)
        OutboxEvent.objects.create(
            aggregate_type="refund",
            aggregate_id=refund.id,
            event_type="refund.succeeded",
            payload={"refund_id": str(refund.id), "booking_id": refund.booking.public_id},
        )
    elif command == "fail":
        _assert_state(refund, {Refund.Status.PROCESSING})
        refund.status = Refund.Status.FAILED
    elif command == "retry":
        _assert_state(refund, {Refund.Status.FAILED})
        refund.status = Refund.Status.PROCESSING
    elif command == "cancel":
        _assert_state(refund, {Refund.Status.REQUESTED})
        refund.status = Refund.Status.CANCELLED
        refund.completed_at = now
    else:
        raise DomainAPIException("VALIDATION_ERROR", details={"command": "unsupported"})

    refund.save()
    record_audit(
        action=f"refund.{command}",
        object_type="refund",
        object_id=refund.id,
        actor_user=actor,
        office_id=refund.booking.office_id,
        request=request,
        before=before,
        after={
            "status": refund.status,
            "approved_amount": str(refund.approved_amount) if refund.approved_amount is not None else None,
        },
    )
    return serialize_refund(refund)
