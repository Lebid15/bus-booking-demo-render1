from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from auditlog.services import record_audit
from bookings.models import Booking
from common.models import OutboxEvent
from identity.crypto import decrypt_secret, encrypt_secret
from identity.models import User
from notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationEscalation,
    NotificationPreference,
    NotificationTemplate,
    PushSubscription,
)
from organizations.models import Office
from support.models import SupportCase, SupportMessage
from tickets.models import Ticket


@dataclass(frozen=True)
class EventRule:
    template_code: str
    channels: tuple[str, ...]
    critical: bool = True
    action_required: bool = False
    action_url: str | None = None


@dataclass(frozen=True)
class Recipient:
    recipient_type: str
    recipient_id: uuid.UUID
    language: str
    booking: Booking | None = None
    user: User | None = None
    office: Office | None = None


@dataclass(frozen=True)
class ProviderResult:
    success: bool
    provider_message_id: str | None = None
    error_code: str | None = None
    permanent: bool = False


EVENT_RULES: dict[str, EventRule] = {
    "booking.created": EventRule(
        "booking_created_unpaid", ("in_app", "email"), action_required=True, action_url="/manage-booking"
    ),
    "payment.manual_transfer.submitted": EventRule("payment_manual_under_review", ("in_app", "email")),
    "payment.confirmed": EventRule("payment_confirmed", ("in_app", "email")),
    "booking.payment_deadline_expired": EventRule("booking_cancelled", ("in_app", "email")),
    "booking.cancellation_requested": EventRule("booking_cancelled", ("in_app", "email")),
    "ticket.reissued": EventRule("ticket_reissued", ("in_app", "email")),
    "support.p1.auto_escalated": EventRule("support_p1_opened", ("in_app", "email")),
    "support.case.sla_escalated": EventRule("support_p1_opened", ("in_app", "email")),
    "refund.processing_requested": EventRule("refund_initiated", ("in_app", "email")),
    "refund.succeeded": EventRule("refund_completed", ("in_app", "email")),
    "trip.cancellation_action_required": EventRule(
        "trip_cancelled",
        ("in_app", "email", "sms"),
        action_required=True,
        action_url="/manage-booking",
    ),
    "trip.vehicle_reallocated": EventRule(
        "trip_material_change_response_required",
        ("in_app", "email", "sms"),
        action_required=True,
        action_url="/manage-booking",
    ),
    "office.payout.change_requested": EventRule("payout_account_change_requested", ("in_app", "email")),
    "office.payout.change_activated": EventRule("payout_account_change_activated", ("in_app", "email")),
    "office.staff.invited": EventRule("office_staff_invited", ("in_app", "email")),
    "office.verification.status_changed": EventRule("office_verification_status_changed", ("in_app", "email")),
}

DEFAULT_TEMPLATE_TEXT: dict[str, tuple[str, str]] = {
    "booking_created_unpaid": ("تم إنشاء حجزك {pnr}", "تم إنشاء الحجز {pnr}. أكمل الدفع قبل {payment_deadline_at}."),
    "payment_manual_under_review": ("التحويل قيد المراجعة", "استلمنا إثبات التحويل للحجز {pnr} وهو قيد المراجعة."),
    "payment_confirmed": ("تم تأكيد الدفع", "تم تأكيد دفع الحجز {pnr}."),
    "booking_cancelled": ("تم تحديث حالة الحجز", "تم إلغاء أو انتهاء الحجز {pnr}."),
    "trip_material_change_response_required": (
        "تغيير جوهري على رحلتك",
        "طرأ تغيير جوهري على الرحلة. يلزم اختيار القبول أو البديل أو الاسترداد.",
    ),
    "trip_cancelled": ("أُلغيت الرحلة", "أُلغيت الرحلة المرتبطة بالحجز {pnr}. اختر البديل أو الاسترداد."),
    "ticket_reissued": ("صدرت تذكرة جديدة", "تم إبطال الإصدار السابق وإصدار تذكرة جديدة للحجز {pnr}."),
    "support_p1_opened": ("حالة دعم عاجلة", "فُتحت أو صُعّدت حالة دعم عاجلة تتطلب المتابعة."),
    "refund_initiated": ("بدأت معالجة الاسترداد", "بدأت معالجة استرداد الحجز {pnr}."),
    "refund_completed": ("اكتمل الاسترداد", "اكتملت عملية استرداد الحجز {pnr}."),
    "payout_account_change_requested": ("طلب تغيير حساب التسوية", "تم طلب تغيير حساب التسوية ويحتاج إلى اعتماد."),
    "payout_account_change_activated": ("تم تفعيل حساب التسوية", "تم تفعيل حساب التسوية الجديد."),
    "office_staff_invited": ("دعوة للانضمام إلى مكتب", "تمت دعوتك للانضمام إلى فريق المكتب."),
    "office_verification_status_changed": ("تغيرت حالة اعتماد المكتب", "تم تحديث حالة اعتماد المكتب إلى {status}."),
    "account_verification": ("رمز التحقق", "استخدم رمز التحقق لإكمال إنشاء الحساب."),
}

ENGLISH_TEMPLATE_TEXT: dict[str, tuple[str, str]] = {
    "booking_created_unpaid": (
        "Booking {pnr} created",
        "Your booking {pnr} was created. Complete payment before {payment_deadline_at}.",
    ),
    "payment_manual_under_review": ("Transfer under review", "We received the transfer proof for booking {pnr}."),
    "payment_confirmed": ("Payment confirmed", "Payment for booking {pnr} has been confirmed."),
    "booking_cancelled": ("Booking status updated", "Booking {pnr} has been cancelled or expired."),
    "trip_material_change_response_required": (
        "Important trip change",
        "Your trip changed materially. Choose accept, alternative, or refund.",
    ),
    "trip_cancelled": ("Trip cancelled", "The trip for booking {pnr} was cancelled. Choose an alternative or refund."),
    "ticket_reissued": (
        "New ticket issued",
        "The previous ticket was revoked and a new ticket was issued for booking {pnr}.",
    ),
    "support_p1_opened": ("Urgent support case", "An urgent support case was opened or escalated."),
    "refund_initiated": ("Refund started", "Refund processing started for booking {pnr}."),
    "refund_completed": ("Refund completed", "Refund processing completed for booking {pnr}."),
    "payout_account_change_requested": (
        "Payout account change requested",
        "A payout account change is awaiting approval.",
    ),
    "payout_account_change_activated": ("Payout account activated", "The new payout account is active."),
    "office_staff_invited": ("Office invitation", "You were invited to join an office team."),
    "office_verification_status_changed": (
        "Office verification updated",
        "Office verification status changed to {status}.",
    ),
    "account_verification": ("Verification code", "Use the verification code to complete account creation."),
}


class _SafeFormat(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def seed_default_templates() -> int:
    created = 0
    now = timezone.now() - timedelta(seconds=1)
    for language, catalogue in (("ar", DEFAULT_TEMPLATE_TEXT), ("en", ENGLISH_TEMPLATE_TEXT)):
        for code, (subject, body) in catalogue.items():
            for channel in NotificationTemplate.Channel.values:
                _, was_created = NotificationTemplate.objects.get_or_create(
                    code=code,
                    channel=channel,
                    language=language,
                    version=1,
                    defaults={
                        "subject_template": subject,
                        "body_template": body,
                        "status": NotificationTemplate.Status.PUBLISHED,
                        "effective_from": now,
                    },
                )
                created += int(was_created)
    return created


def _template(code: str, channel: str, language: str) -> NotificationTemplate:
    now = timezone.now()
    template = (
        NotificationTemplate.objects.filter(
            code=code,
            channel=channel,
            language=language,
            status=NotificationTemplate.Status.PUBLISHED,
            effective_from__lte=now,
        )
        .order_by("-version")
        .first()
    )
    if template is None and language != "ar":
        template = (
            NotificationTemplate.objects.filter(
                code=code,
                channel=channel,
                language="ar",
                status=NotificationTemplate.Status.PUBLISHED,
                effective_from__lte=now,
            )
            .order_by("-version")
            .first()
        )
    if template is None:
        seed_default_templates()
        template = (
            NotificationTemplate.objects.filter(
                code=code,
                channel=channel,
                language=language if language in {"ar", "en"} else "ar",
                status=NotificationTemplate.Status.PUBLISHED,
            )
            .order_by("-version")
            .first()
        )
    if template is None:
        raise RuntimeError(f"Missing notification template: {code}/{channel}/{language}")
    return template


def _booking_from_event(event: OutboxEvent) -> Booking | None:
    booking_id = event.payload.get("booking_id")
    if booking_id:
        booking = (
            Booking.objects.select_related("customer_user", "office", "trip").filter(public_id=str(booking_id)).first()
        )
        if booking is not None:
            return booking
    if event.aggregate_type == "booking":
        return Booking.objects.select_related("customer_user", "office", "trip").filter(id=event.aggregate_id).first()
    if event.aggregate_type == "ticket":
        ticket = (
            Ticket.objects.select_related(
                "passenger__booking__customer_user", "passenger__booking__office", "passenger__booking__trip"
            )
            .filter(id=event.aggregate_id)
            .first()
        )
        return ticket.passenger.booking if ticket is not None else None
    return None


def _office_from_value(value: object) -> Office | None:
    if value is None:
        return None
    raw = str(value)
    try:
        parsed = uuid.UUID(raw)
    except ValueError:
        parsed = None
    query = Office.objects.filter(id=parsed) if parsed else Office.objects.filter(public_id=raw)
    return query.first()


def _user_from_value(value: object) -> User | None:
    if value is None:
        return None
    raw = str(value)
    try:
        return User.objects.filter(id=uuid.UUID(raw)).first()
    except ValueError:
        return User.objects.filter(public_id=raw).first()


def _recipient(event: OutboxEvent) -> Recipient | None:
    booking = _booking_from_event(event)
    if booking is not None:
        if booking.customer_user is not None:
            return Recipient(
                recipient_type=Notification.RecipientType.USER,
                recipient_id=cast(uuid.UUID, booking.customer_user_id),
                language=booking.customer_user.preferred_language or "ar",
                booking=booking,
                user=booking.customer_user,
                office=booking.office,
            )
        return Recipient(
            recipient_type=Notification.RecipientType.BOOKING_CONTACT,
            recipient_id=booking.id,
            language=str(event.payload.get("language") or "ar"),
            booking=booking,
            office=booking.office,
        )
    if user := _user_from_value(event.payload.get("user_id")):
        return Recipient(
            recipient_type=Notification.RecipientType.USER,
            recipient_id=user.id,
            language=user.preferred_language or "ar",
            user=user,
        )
    if office := _office_from_value(event.payload.get("office_id")):
        return Recipient(
            recipient_type=Notification.RecipientType.OFFICE,
            recipient_id=office.id,
            language=str(event.payload.get("language") or "ar"),
            office=office,
        )
    return None


def _rule(event: OutboxEvent) -> EventRule | None:
    if event.event_type == "notification.requested":
        code = str(event.payload.get("template") or "")
        if not code:
            return None
        raw_channel = str(event.payload.get("channel") or "")
        channel = {"phone": "sms"}.get(raw_channel, raw_channel)
        channels = (channel,) if channel in NotificationTemplate.Channel.values else ("in_app", "email")
        action_required = code in {"trip_material_change_response_required", "trip_cancelled"}
        return EventRule(
            code,
            channels,
            critical=True,
            action_required=action_required,
            action_url="/manage-booking" if action_required else None,
        )
    return EVENT_RULES.get(event.event_type)


def _context(event: OutboxEvent, recipient: Recipient) -> dict[str, object]:
    context: dict[str, object] = dict(event.payload)
    if recipient.booking is not None:
        context.update(
            {
                "booking_id": recipient.booking.public_id,
                "pnr": recipient.booking.pnr,
                "payment_deadline_at": recipient.booking.payment_deadline_at.isoformat()
                if recipient.booking.payment_deadline_at
                else "",
                "trip_id": recipient.booking.trip.public_id,
            }
        )
    return context


def _destination(recipient: Recipient, channel: str) -> str | None:
    if channel == NotificationTemplate.Channel.IN_APP:
        return None
    if channel == NotificationTemplate.Channel.EMAIL:
        if recipient.user and recipient.user.email:
            return recipient.user.email
        if recipient.booking and recipient.booking.contact_email:
            return recipient.booking.contact_email
        if recipient.office and recipient.office.support_email:
            return recipient.office.support_email
    if channel == NotificationTemplate.Channel.SMS:
        if recipient.user and recipient.user.phone_e164:
            return recipient.user.phone_e164
        if recipient.booking and recipient.booking.contact_phone:
            return recipient.booking.contact_phone
        if recipient.office and recipient.office.support_phone:
            return recipient.office.support_phone
    if channel == NotificationTemplate.Channel.PUSH and recipient.user:
        subscription = (
            recipient.user.push_subscriptions.filter(status=PushSubscription.Status.ACTIVE)
            .order_by("-created_at")
            .first()
        )
        if subscription is not None:
            return decrypt_secret(bytes(subscription.token_ciphertext))
    return None


def _channel_allowed(recipient: Recipient, event_type: str, channel: str, *, critical: bool) -> bool:
    if channel == NotificationTemplate.Channel.IN_APP and critical:
        return True
    if recipient.user is None:
        return True
    preference = NotificationPreference.objects.filter(
        user=recipient.user,
        event_type=event_type,
        channel=channel,
    ).first()
    return preference.enabled if preference is not None else True


def _semantic_key(event: OutboxEvent, recipient: Recipient, channel: str, template: NotificationTemplate) -> str:
    raw = "|".join(
        [
            event.event_type,
            event.aggregate_type,
            str(event.aggregate_id),
            recipient.recipient_type,
            str(recipient.recipient_id),
            channel,
            template.code,
            str(template.version),
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _destination_fields(destination: str | None) -> tuple[bytes | None, bytes | None]:
    if not destination:
        return None, None
    return hashlib.sha256(destination.strip().lower().encode()).digest(), encrypt_secret(destination)


@transaction.atomic
def create_notifications_for_event(event: OutboxEvent) -> list[Notification]:
    rule = _rule(event)
    recipient = _recipient(event)
    if rule is None or recipient is None:
        return []
    context = _context(event, recipient)
    created_notifications: list[Notification] = []
    for channel in rule.channels:
        if not _channel_allowed(recipient, event.event_type, channel, critical=rule.critical):
            continue
        destination = _destination(recipient, channel)
        if channel != NotificationTemplate.Channel.IN_APP and destination is None:
            continue
        template = _template(rule.template_code, channel, recipient.language)
        dedupe_key = _semantic_key(event, recipient, channel, template)
        subject = template.subject_template.format_map(_SafeFormat(context))
        body = template.body_template.format_map(_SafeFormat(context))
        try:
            notification, created = Notification.objects.get_or_create(
                dedupe_key=dedupe_key,
                defaults={
                    "source_event_id": event.id,
                    "event_type": event.event_type,
                    "recipient_type": recipient.recipient_type,
                    "recipient_id": recipient.recipient_id,
                    "booking": recipient.booking,
                    "template": template,
                    "language": template.language,
                    "payload": context,
                    "rendered_subject": subject,
                    "rendered_body": body,
                    "action_required": rule.action_required,
                    "action_url": rule.action_url,
                },
            )
        except IntegrityError:
            notification = Notification.objects.get(dedupe_key=dedupe_key)
            created = False
        if not created:
            created_notifications.append(notification)
            continue
        destination_hash, destination_ciphertext = _destination_fields(destination)
        NotificationDelivery.objects.create(
            notification=notification,
            channel=channel,
            destination_hash=destination_hash,
            destination_ciphertext=destination_ciphertext,
            status=NotificationDelivery.Status.QUEUED,
            attempt_no=1,
            next_attempt_at=timezone.now(),
        )
        created_notifications.append(notification)
    return created_notifications


@transaction.atomic
def dispatch_outbox_events(*, limit: int = 100) -> int:
    recognized = set(EVENT_RULES) | {"notification.requested"}
    events = list(
        OutboxEvent.objects.select_for_update()
        .filter(published_at__isnull=True, event_type__in=recognized)
        .filter(next_attempt_at__isnull=True)
        .order_by("occurred_at", "id")[:limit]
    )
    dispatched = 0
    for event in events:
        try:
            create_notifications_for_event(event)
            event.published_at = timezone.now()
            event.attempt_count += 1
            event.save(update_fields=["published_at", "attempt_count"])
            dispatched += 1
        except Exception:
            event.attempt_count += 1
            event.next_attempt_at = timezone.now() + timedelta(seconds=min(300, 2 ** min(event.attempt_count, 8)))
            event.save(update_fields=["attempt_count", "next_attempt_at"])
            raise
    return dispatched


def _send_external(delivery: NotificationDelivery) -> ProviderResult:
    channel = delivery.channel
    forced = {
        item.strip()
        for item in str(getattr(settings, "NOTIFICATION_FORCE_FAILURE_CHANNELS", "")).split(",")
        if item.strip()
    }
    destination = decrypt_secret(bytes(delivery.destination_ciphertext)) if delivery.destination_ciphertext else ""
    if not destination:
        return ProviderResult(False, error_code="DESTINATION_MISSING", permanent=True)
    if "invalid" in destination.lower():
        return ProviderResult(False, error_code="DESTINATION_INVALID", permanent=True)
    if channel in forced:
        return ProviderResult(False, error_code="PROVIDER_TEMPORARY_FAILURE")
    provider_id = f"mock-{channel}-{uuid.uuid4().hex}"
    return ProviderResult(True, provider_message_id=provider_id)


def _refresh_notification(notification: Notification) -> None:
    latest: dict[str, NotificationDelivery] = {}
    for row in notification.deliveries.order_by("channel", "-attempt_no"):
        latest.setdefault(row.channel, row)
    statuses = {row.status for row in latest.values()}
    if statuses and statuses <= {NotificationDelivery.Status.SENT, NotificationDelivery.Status.DELIVERED}:
        notification.status = Notification.Status.SENT
    elif NotificationDelivery.Status.DELIVERED in statuses or NotificationDelivery.Status.SENT in statuses:
        notification.status = Notification.Status.PARTIALLY_SENT
    elif statuses and statuses <= {
        NotificationDelivery.Status.FAILED,
        NotificationDelivery.Status.BOUNCED,
        NotificationDelivery.Status.CANCELLED,
    }:
        notification.status = Notification.Status.FAILED
    else:
        notification.status = Notification.Status.QUEUED
    notification.save(update_fields=["status"])


def _fallback_channel(notification: Notification, failed_channel: str) -> str | None:
    if (
        failed_channel == NotificationTemplate.Channel.EMAIL
        and notification.booking
        and notification.booking.contact_phone
    ):
        return NotificationTemplate.Channel.SMS
    return None


def _recipient_from_notification(notification: Notification) -> Recipient:
    booking = notification.booking
    if notification.recipient_id is None:
        raise RuntimeError("Notification recipient_id is required for delivery")
    user = (
        User.objects.filter(id=notification.recipient_id).first()
        if notification.recipient_type == Notification.RecipientType.USER
        else None
    )
    office = (
        Office.objects.filter(id=notification.recipient_id).first()
        if notification.recipient_type == Notification.RecipientType.OFFICE
        else (booking.office if booking else None)
    )
    return Recipient(
        recipient_type=notification.recipient_type,
        recipient_id=notification.recipient_id,
        language=notification.language,
        booking=booking,
        user=user,
        office=office,
    )


@transaction.atomic
def _create_fallback(notification: Notification, channel: str) -> Notification | None:
    recipient = _recipient_from_notification(notification)
    destination = _destination(recipient, channel)
    if destination is None:
        return None
    template = _template(notification.template.code, channel, notification.language)
    raw = f"{notification.dedupe_key}|fallback|{channel}|{template.version}"
    dedupe_key = hashlib.sha256(raw.encode()).hexdigest()
    fallback, created = Notification.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "source_event_id": notification.source_event_id,
            "event_type": notification.event_type,
            "recipient_type": notification.recipient_type,
            "recipient_id": notification.recipient_id,
            "booking": notification.booking,
            "template": template,
            "language": template.language,
            "payload": notification.payload,
            "rendered_subject": template.subject_template.format_map(_SafeFormat(notification.payload)),
            "rendered_body": template.body_template.format_map(_SafeFormat(notification.payload)),
            "action_required": notification.action_required,
            "action_url": notification.action_url,
        },
    )
    if created:
        destination_hash, destination_ciphertext = _destination_fields(destination)
        NotificationDelivery.objects.create(
            notification=fallback,
            channel=channel,
            destination_hash=destination_hash,
            destination_ciphertext=destination_ciphertext,
            next_attempt_at=timezone.now(),
        )
    return fallback


@transaction.atomic
def _escalate(notification: Notification, reason_code: str) -> NotificationEscalation:
    existing = NotificationEscalation.objects.select_related("support_case").filter(notification=notification).first()
    if existing is not None:
        return existing
    booking = notification.booking
    support_case = None
    if booking is not None:
        support_case = SupportCase.objects.create(
            booking=booking,
            trip=booking.trip,
            office=booking.office,
            priority=SupportCase.Priority.P1,
            category="notification_delivery_failure",
            status=SupportCase.Status.ESCALATED,
            sla_due_at=timezone.now() + timedelta(minutes=15),
            metadata={"notification_id": str(notification.id), "reason_code": reason_code},
        )
        SupportMessage.objects.create(
            case=support_case,
            sender_type=SupportMessage.SenderType.SYSTEM,
            visibility=SupportMessage.Visibility.INTERNAL,
            body="تعذر تسليم إشعار حرج بعد استنفاد المحاولات؛ يلزم تواصل بشري أو قناة بديلة.",
        )
    escalation = NotificationEscalation.objects.create(
        notification=notification,
        support_case=support_case,
        reason_code=reason_code,
    )
    record_audit(
        action="system.notification.escalated",
        object_type="notification",
        object_id=notification.id,
        actor_type="system",
        office_id=booking.office_id if booking else None,
        after={"reason_code": reason_code, "support_case_id": str(support_case.id) if support_case else None},
    )
    return escalation


@transaction.atomic
def process_delivery(delivery_id: uuid.UUID) -> bool:
    delivery = (
        NotificationDelivery.objects.select_for_update(of=("self",))
        .select_related("notification__template", "notification__booking__trip", "notification__booking__office")
        .filter(id=delivery_id)
        .first()
    )
    if delivery is None or delivery.status not in {
        NotificationDelivery.Status.QUEUED,
        NotificationDelivery.Status.FAILED,
    }:
        return False
    if delivery.next_attempt_at and delivery.next_attempt_at > timezone.now():
        return False
    delivery.status = NotificationDelivery.Status.SENDING
    delivery.save(update_fields=["status"])
    now = timezone.now()
    if delivery.channel == NotificationTemplate.Channel.IN_APP:
        result = ProviderResult(True, provider_message_id=f"in-app-{delivery.id}")
    else:
        result = _send_external(delivery)
    if result.success:
        delivery.status = NotificationDelivery.Status.DELIVERED
        delivery.provider_message_id = result.provider_message_id
        delivery.sent_at = now
        delivery.delivered_at = now
        delivery.error_code = None
        delivery.save(update_fields=["status", "provider_message_id", "sent_at", "delivered_at", "error_code"])
        _refresh_notification(delivery.notification)
        return True

    delivery.status = NotificationDelivery.Status.FAILED
    delivery.error_code = result.error_code
    delivery.permanent_failure = result.permanent
    delivery.save(update_fields=["status", "error_code", "permanent_failure"])
    max_attempts = int(getattr(settings, "NOTIFICATION_MAX_ATTEMPTS", 4))
    if not result.permanent and delivery.attempt_no < max_attempts:
        delay = min(
            int(getattr(settings, "NOTIFICATION_RETRY_MAX_SECONDS", 3600)),
            int(getattr(settings, "NOTIFICATION_RETRY_BASE_SECONDS", 30)) * (2 ** (delivery.attempt_no - 1)),
        )
        NotificationDelivery.objects.get_or_create(
            notification=delivery.notification,
            channel=delivery.channel,
            attempt_no=delivery.attempt_no + 1,
            defaults={
                "destination_hash": delivery.destination_hash,
                "destination_ciphertext": delivery.destination_ciphertext,
                "next_attempt_at": now + timedelta(seconds=delay),
            },
        )
    else:
        fallback = _fallback_channel(delivery.notification, delivery.channel)
        if fallback is not None:
            _create_fallback(delivery.notification, fallback)
        _escalate(delivery.notification, result.error_code or "DELIVERY_EXHAUSTED")
    _refresh_notification(delivery.notification)
    return False


@transaction.atomic
def deliver_due_notifications(*, limit: int = 100) -> int:
    now = timezone.now()
    ids = list(
        NotificationDelivery.objects.filter(
            status__in=[NotificationDelivery.Status.QUEUED, NotificationDelivery.Status.FAILED],
        )
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .order_by("next_attempt_at", "created_at")
        .values_list("id", flat=True)[:limit]
    )
    processed = 0
    for delivery_id in ids:
        processed += int(process_delivery(delivery_id))
    return processed


@transaction.atomic
def update_preferences(*, user: User, rows: Sequence[Mapping[str, object]]) -> list[NotificationPreference]:
    result: list[NotificationPreference] = []
    for row in rows:
        event_type = str(row["event_type"])
        channel = str(row["channel"])
        enabled = bool(row["enabled"])
        preference, _ = NotificationPreference.objects.update_or_create(
            user=user,
            event_type=event_type,
            channel=channel,
            defaults={"enabled": enabled},
        )
        result.append(preference)
    return result


@transaction.atomic
def register_push_subscription(*, user: User, token: str, platform: str) -> PushSubscription:
    normalized = token.strip()
    token_hash = hashlib.sha256(normalized.encode()).digest()
    subscription, _ = PushSubscription.objects.update_or_create(
        token_hash=token_hash,
        defaults={
            "user": user,
            "platform": platform,
            "token_ciphertext": encrypt_secret(normalized),
            "status": PushSubscription.Status.ACTIVE,
            "revoked_at": None,
        },
    )
    return subscription
