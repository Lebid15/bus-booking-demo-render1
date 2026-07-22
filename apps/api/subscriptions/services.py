from __future__ import annotations

import calendar
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import HttpRequest
from django.utils import timezone

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.models import OutboxEvent
from finance.models import LedgerAccount, LedgerPosting
from finance.services import PostingSpec, money, post_ledger_entry
from identity.models import User
from organizations.models import Office
from organizations.services import OfficeContext, require_fresh_mfa
from subscriptions.models import (
    OfficeSubscription,
    SubscriptionChangeRequest,
    SubscriptionInvoice,
    SubscriptionPlan,
)

COMMERCIAL_STATUSES = {
    OfficeSubscription.Status.TRIAL,
    OfficeSubscription.Status.ACTIVE,
    OfficeSubscription.Status.PAST_DUE,
}
READ_ONLY_STATUSES = {
    OfficeSubscription.Status.GRACE,
    OfficeSubscription.Status.SUSPENDED,
    OfficeSubscription.Status.CANCELLED,
    OfficeSubscription.Status.EXPIRED,
}


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def period_end_for(plan: SubscriptionPlan, start: datetime, *, custom_end: datetime | None = None) -> datetime:
    if plan.billing_period == SubscriptionPlan.BillingPeriod.MONTHLY:
        return _add_months(start, 1)
    if plan.billing_period == SubscriptionPlan.BillingPeriod.QUARTERLY:
        return _add_months(start, 3)
    if plan.billing_period == SubscriptionPlan.BillingPeriod.YEARLY:
        return _add_months(start, 12)
    if custom_end is None or custom_end <= start:
        raise DomainAPIException("VALIDATION_ERROR", details={"reason": "custom_period_end_required"})
    return custom_end


def serialize_plan(plan: SubscriptionPlan) -> dict[str, Any]:
    return {
        "id": plan.public_id,
        "code": plan.code,
        "name": plan.name_ar,
        "billing_period": plan.billing_period,
        "price": {"amount": str(plan.price_amount), "currency": plan.currency},
        "features": plan.features_json,
        "limits": plan.limits_json,
        "status": plan.status,
        "effective_from": plan.effective_from.isoformat(),
        "effective_to": plan.effective_to.isoformat() if plan.effective_to is not None else None,
        "version": plan.version,
    }


def serialize_invoice(invoice: SubscriptionInvoice) -> dict[str, Any]:
    return {
        "id": invoice.public_id,
        "subscription_id": invoice.office_subscription.public_id,
        "office_id": invoice.office.public_id,
        "status": invoice.status,
        "currency": invoice.currency,
        "subtotal_amount": str(invoice.subtotal_amount),
        "tax_amount": str(invoice.tax_amount),
        "total_amount": str(invoice.total_amount),
        "due_at": invoice.due_at,
        "paid_at": invoice.paid_at,
        "payment_reference": invoice.payment_reference,
        "created_at": invoice.created_at,
    }


def current_subscription(office: Office, *, for_update: bool = False) -> OfficeSubscription | None:
    queryset = OfficeSubscription.objects.select_related("plan", "office")
    if for_update:
        queryset = queryset.select_for_update()
    return (
        queryset.filter(office=office, status__in=OfficeSubscription.ACTIVEISH_STATUSES)
        .order_by("-period_start", "-created_at")
        .first()
    )


def subscription_enforcement_enabled() -> bool:
    if not getattr(settings, "SUBSCRIPTION_ENFORCEMENT_ENABLED", True):
        return False
    now = timezone.now()
    return SubscriptionPlan.objects.filter(
        status=SubscriptionPlan.Status.ACTIVE,
        effective_from__lte=now,
    ).filter(models_effective_filter(now)).exists()


def models_effective_filter(now: datetime):  # type: ignore[no-untyped-def]
    from django.db.models import Q

    return Q(effective_to__isnull=True) | Q(effective_to__gt=now)


def commercial_access(office: Office, *, now: datetime | None = None) -> dict[str, Any]:
    current = now or timezone.now()
    if not subscription_enforcement_enabled():
        return {
            "allowed": True,
            "mode": "legacy_unlimited",
            "status": "active",
            "reason": None,
            "subscription": None,
        }
    subscription = current_subscription(office)
    if subscription is None:
        return {
            "allowed": False,
            "mode": "existing_bookings_only",
            "status": "missing",
            "reason": "subscription_required",
            "subscription": None,
        }
    allowed = subscription.status in COMMERCIAL_STATUSES and subscription.period_start <= current
    if subscription.status in {OfficeSubscription.Status.TRIAL, OfficeSubscription.Status.ACTIVE}:
        allowed = allowed and subscription.period_end > current
    reason = None if allowed else f"subscription_{subscription.status}"
    return {
        "allowed": allowed,
        "mode": "commercial" if allowed else "existing_bookings_only",
        "status": subscription.status,
        "reason": reason,
        "subscription": subscription,
    }


def require_new_commercial_operation(office: Office) -> OfficeSubscription | None:
    access = commercial_access(office)
    if not access["allowed"]:
        raise DomainAPIException("SUBSCRIPTION_REQUIRED", details={"reason": access["reason"]})
    value = access["subscription"]
    return value if isinstance(value, OfficeSubscription) else None


def usage_summary(office: Office, subscription: OfficeSubscription | None = None) -> dict[str, Any]:
    from fleet.models import Vehicle
    from organizations.models import OfficeBranch, OfficeMembership
    from trips.models import Trip

    active_subscription = subscription or current_subscription(office)
    limits = active_subscription.limits_snapshot if active_subscription is not None else {}
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    values = {
        "branches": OfficeBranch.objects.filter(office=office, status="active").count(),
        "staff": OfficeMembership.objects.filter(
            office=office,
            status=OfficeMembership.Status.ACTIVE,
            revoked_at__isnull=True,
        ).count(),
        "vehicles": Vehicle.objects.filter(office=office).exclude(status="retired").count(),
        "monthly_trips": Trip.objects.filter(office=office, created_at__gte=month_start).count(),
    }
    limit_map = {
        "branches": "max_branches",
        "staff": "max_staff",
        "vehicles": "max_vehicles",
        "monthly_trips": "max_monthly_trips",
    }
    return {
        key: {
            "used": value,
            "limit": limits.get(limit_map[key]),
            "remaining": None
            if limits.get(limit_map[key]) in (None, 0, "0")
            else max(0, int(limits[limit_map[key]]) - value),
        }
        for key, value in values.items()
    }


def require_usage_capacity(office: Office, metric: str) -> None:
    subscription = require_new_commercial_operation(office)
    if subscription is None:
        return
    usage = usage_summary(office, subscription)
    item = usage.get(metric)
    if item is None:
        return
    limit = item["limit"]
    if limit in (None, 0, "0"):
        return
    if int(item["used"]) >= int(limit):
        raise DomainAPIException("SUBSCRIPTION_LIMIT_REACHED", details={"metric": metric, "limit": int(limit)})


def serialize_subscription(subscription: OfficeSubscription, *, include_usage: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": subscription.public_id,
        "office_id": subscription.office.public_id,
        "plan": serialize_plan(subscription.plan),
        "status": subscription.status,
        "period_start": subscription.period_start,
        "period_end": subscription.period_end,
        "price_snapshot": subscription.price_snapshot,
        "features": subscription.features_snapshot,
        "limits": subscription.limits_snapshot,
        "auto_renew": subscription.auto_renew,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "access_mode": commercial_access(subscription.office)["mode"],
        "invoices": [serialize_invoice(invoice) for invoice in subscription.invoices.order_by("-created_at")[:12]],
    }
    if include_usage:
        payload["usage"] = usage_summary(subscription.office, subscription)
    return payload


def _validate_active_plan(plan: SubscriptionPlan, at: datetime) -> None:
    if plan.status != SubscriptionPlan.Status.ACTIVE or plan.effective_from > at:
        raise DomainAPIException("VALIDATION_ERROR", details={"reason": "subscription_plan_not_active"})
    if plan.effective_to is not None and plan.effective_to <= at:
        raise DomainAPIException("VALIDATION_ERROR", details={"reason": "subscription_plan_expired"})


def _price_snapshot(plan: SubscriptionPlan) -> dict[str, Any]:
    return {
        "plan_id": plan.public_id,
        "plan_code": plan.code,
        "plan_version": plan.version,
        "amount": str(plan.price_amount),
        "currency": plan.currency,
        "billing_period": plan.billing_period,
        "captured_at": timezone.now().isoformat(),
    }


def create_subscription_invoice(
    subscription: OfficeSubscription,
    *, due_at: datetime | None = None,
    tax_amount: Decimal | str = Decimal("0.00"),
) -> SubscriptionInvoice | None:
    subtotal = money(subscription.price_snapshot.get("amount", "0"))
    tax = money(tax_amount)
    total = money(subtotal + tax)
    if total <= 0:
        return None
    invoice = SubscriptionInvoice.objects.create(
        office_subscription=subscription,
        office=subscription.office,
        status=SubscriptionInvoice.Status.OPEN,
        currency=str(subscription.price_snapshot["currency"]),
        subtotal_amount=subtotal,
        tax_amount=tax,
        total_amount=total,
        due_at=due_at or timezone.now() + timedelta(days=int(getattr(settings, "SUBSCRIPTION_INVOICE_DUE_DAYS", 7))),
    )
    entry = post_ledger_entry(
        event_type="SUBSCRIPTION_INVOICED",
        event_id=invoice.id,
        office=subscription.office,
        currency=invoice.currency,
        occurred_at=timezone.now(),
        description=f"Subscription invoice {invoice.public_id}",
        postings=[
            PostingSpec(
                account_code="1030_OTHER_RECEIVABLE",
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.DEBIT,
                amount=total,
                office_scoped=True,
            ),
            PostingSpec(
                account_code="4010_SUBSCRIPTION_REVENUE",
                account_type=LedgerAccount.AccountType.REVENUE,
                direction=LedgerPosting.Direction.CREDIT,
                amount=total,
            ),
        ],
    )
    invoice.ledger_entry = entry
    invoice.save(update_fields=["ledger_entry"])
    OutboxEvent.objects.create(
        aggregate_type="subscription_invoice",
        aggregate_id=invoice.id,
        event_type="subscription.invoice.opened",
        payload={"invoice_id": invoice.public_id, "office_id": subscription.office.public_id, "total": str(total)},
    )
    return invoice


@transaction.atomic
def mark_invoice_paid(
    *,
    invoice: SubscriptionInvoice,
    payment_reference: str,
    actor: User,
    request: HttpRequest | None,
    idempotency_key: str,
) -> SubscriptionInvoice:
    locked = (
        SubscriptionInvoice.objects.select_for_update()
        .select_related("office_subscription", "office")
        .get(id=invoice.id)
    )
    payload = {"payment_reference": payment_reference}
    idem, replay = begin_idempotency(
        scope_type="subscription_invoice_payment", scope_id=locked.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionInvoice.objects.get(public_id=replay["invoice_id"])
    if locked.status == SubscriptionInvoice.Status.PAID:
        if locked.payment_reference != payment_reference:
            raise DomainAPIException("PAYMENT_ALREADY_SUCCEEDED")
        complete_idempotency(idem, {"invoice_id": locked.public_id})
        return locked
    if locked.status != SubscriptionInvoice.Status.OPEN:
        raise DomainAPIException("PAYMENT_STATE_CONFLICT")
    if SubscriptionInvoice.objects.exclude(id=locked.id).filter(payment_reference=payment_reference).exists():
        raise DomainAPIException("PAYMENT_ALREADY_SUCCEEDED", details={"reason": "payment_reference_duplicate"})
    payment_entry = post_ledger_entry(
        event_type="SUBSCRIPTION_PAID",
        event_id=locked.id,
        office=locked.office,
        currency=locked.currency,
        occurred_at=timezone.now(),
        description=f"Subscription invoice payment {locked.public_id}",
        postings=[
            PostingSpec(
                account_code="1000_BANK",
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.DEBIT,
                amount=locked.total_amount,
            ),
            PostingSpec(
                account_code="1030_OTHER_RECEIVABLE",
                account_type=LedgerAccount.AccountType.ASSET,
                direction=LedgerPosting.Direction.CREDIT,
                amount=locked.total_amount,
                office_scoped=True,
            ),
        ],
    )
    now = timezone.now()
    locked.status = SubscriptionInvoice.Status.PAID
    locked.paid_at = now
    locked.payment_reference = payment_reference
    locked.payment_ledger_entry = payment_entry
    locked.save(update_fields=["status", "paid_at", "payment_reference", "payment_ledger_entry"])
    subscription = locked.office_subscription
    if subscription.status in {OfficeSubscription.Status.PAST_DUE, OfficeSubscription.Status.GRACE}:
        subscription.status = OfficeSubscription.Status.ACTIVE
        subscription.save(update_fields=["status"])
    record_audit(
        action="platform.subscription.invoice.paid",
        object_type="subscription_invoice",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        before={"status": SubscriptionInvoice.Status.OPEN},
        after={"status": locked.status, "payment_reference": payment_reference},
    )
    OutboxEvent.objects.create(
        aggregate_type="subscription_invoice",
        aggregate_id=locked.id,
        event_type="subscription.invoice.paid",
        payload={"invoice_id": locked.public_id, "office_id": locked.office.public_id},
    )
    complete_idempotency(idem, {"invoice_id": locked.public_id})
    return locked


@transaction.atomic
def create_plan(
    *, actor: User, request: HttpRequest, data: dict[str, Any], idempotency_key: str
) -> SubscriptionPlan:
    require_fresh_mfa(request)
    payload = dict(data)
    idem, replay = begin_idempotency(
        scope_type="subscription_plan_create", scope_id=None, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionPlan.objects.get(public_id=replay["plan_id"])
    plan = SubscriptionPlan.objects.create(
        code=str(data["code"]),
        name_ar=str(data["name"]),
        billing_period=str(data["billing_period"]),
        price_amount=money(data["price_amount"]),
        currency=str(data["currency"]).upper(),
        features_json=data.get("features", {}),
        limits_json=data.get("limits", {}),
        status=str(data.get("status", SubscriptionPlan.Status.DRAFT)),
        effective_from=data.get("effective_from") or timezone.now(),
        effective_to=data.get("effective_to"),
        created_by=actor,
    )
    plan.full_clean()
    record_audit(
        action="platform.subscription_plan.created",
        object_type="subscription_plan",
        object_id=plan.id,
        actor_user=actor,
        request=request,
        after=serialize_plan(plan),
    )
    complete_idempotency(idem, {"plan_id": plan.public_id})
    return plan


@transaction.atomic
def update_plan(
    *, plan: SubscriptionPlan, actor: User, request: HttpRequest, data: dict[str, Any], idempotency_key: str
) -> SubscriptionPlan:
    require_fresh_mfa(request)
    locked = SubscriptionPlan.objects.select_for_update().get(id=plan.id)
    payload = dict(data)
    idem, replay = begin_idempotency(
        scope_type="subscription_plan_update", scope_id=locked.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionPlan.objects.get(public_id=replay["plan_id"])
    expected_version = int(data.get("version", locked.version))
    if expected_version != locked.version:
        raise DomainAPIException("VERSION_CONFLICT")
    before = serialize_plan(locked)
    mapping = {
        "name": "name_ar",
        "billing_period": "billing_period",
        "price_amount": "price_amount",
        "currency": "currency",
        "features": "features_json",
        "limits": "limits_json",
        "status": "status",
        "effective_from": "effective_from",
        "effective_to": "effective_to",
    }
    for source, target in mapping.items():
        if source in data:
            value = data[source]
            if source == "price_amount":
                value = money(value)
            if source == "currency":
                value = str(value).upper()
            setattr(locked, target, value)
    locked.version += 1
    locked.full_clean()
    locked.save()
    record_audit(
        action="platform.subscription_plan.updated",
        object_type="subscription_plan",
        object_id=locked.id,
        actor_user=actor,
        request=request,
        before=before,
        after=serialize_plan(locked),
        metadata={"historical_subscription_snapshots_preserved": True},
    )
    complete_idempotency(idem, {"plan_id": locked.public_id})
    return locked


@transaction.atomic
def assign_subscription(
    *,
    office: Office,
    plan: SubscriptionPlan,
    actor: User,
    request: HttpRequest | None,
    idempotency_key: str,
    requested_status: str = OfficeSubscription.Status.ACTIVE,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    auto_renew: bool = False,
    payment_reference: str | None = None,
    source: str = "platform",
) -> OfficeSubscription:
    locked_office = Office.objects.select_for_update().get(id=office.id)
    locked_plan = SubscriptionPlan.objects.select_for_update().get(id=plan.id)
    start = period_start or timezone.now()
    _validate_active_plan(locked_plan, start)
    end = period_end_for(locked_plan, start, custom_end=period_end)
    payload = {
        "plan_id": locked_plan.public_id,
        "requested_status": requested_status,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "auto_renew": auto_renew,
        "payment_reference": payment_reference,
        "source": source,
    }
    idem, replay = begin_idempotency(
        scope_type="office_subscription_assign", scope_id=locked_office.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return OfficeSubscription.objects.get(public_id=replay["subscription_id"])
    if requested_status == OfficeSubscription.Status.TRIAL and OfficeSubscription.objects.filter(
        office=locked_office, source="trial"
    ).exists():
        raise DomainAPIException("SUBSCRIPTION_TRIAL_ALREADY_USED")
    previous = current_subscription(locked_office, for_update=True)
    if previous is not None:
        previous.status = OfficeSubscription.Status.CANCELLED
        previous.cancel_at_period_end = True
        previous.save(update_fields=["status", "cancel_at_period_end"])
    price = _price_snapshot(locked_plan)
    initial_status = requested_status
    if (
        requested_status != OfficeSubscription.Status.TRIAL
        and money(locked_plan.price_amount) > 0
        and not payment_reference
    ):
        initial_status = OfficeSubscription.Status.PAST_DUE
    subscription = OfficeSubscription.objects.create(
        office=locked_office,
        plan=locked_plan,
        status=initial_status,
        period_start=start,
        period_end=end,
        price_snapshot=price,
        features_snapshot=dict(locked_plan.features_json),
        limits_snapshot=dict(locked_plan.limits_json),
        auto_renew=auto_renew,
        source="trial" if requested_status == OfficeSubscription.Status.TRIAL else source,
    )
    invoice = None
    if requested_status != OfficeSubscription.Status.TRIAL:
        invoice = create_subscription_invoice(subscription)
        if invoice is not None and payment_reference:
            invoice = mark_invoice_paid(
                invoice=invoice,
                payment_reference=payment_reference,
                actor=actor,
                request=request,
                idempotency_key=f"{idempotency_key}:payment",
            )
    record_audit(
        action="platform.office.subscription.assigned",
        object_type="office_subscription",
        object_id=subscription.id,
        actor_user=actor,
        office_id=locked_office.id,
        request=request,
        before={"subscription_id": previous.public_id if previous else None},
        after={
            "subscription_id": subscription.public_id,
            "plan_id": locked_plan.public_id,
            "status": subscription.status,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "snapshot": price,
        },
    )
    OutboxEvent.objects.create(
        aggregate_type="office_subscription",
        aggregate_id=subscription.id,
        event_type="subscription.assigned",
        payload={
            "subscription_id": subscription.public_id,
            "office_id": locked_office.public_id,
            "status": subscription.status,
            "existing_bookings_preserved": True,
        },
    )
    complete_idempotency(idem, {"subscription_id": subscription.public_id})
    return subscription


@transaction.atomic
def request_change(
    *, context: OfficeContext, actor: User, request: HttpRequest, plan: SubscriptionPlan, effective_mode: str,
    idempotency_key: str
) -> SubscriptionChangeRequest:
    current = current_subscription(context.office, for_update=True)
    if current is None:
        raise DomainAPIException("PAYMENT_REQUIRED", details={"reason": "subscription_missing"})
    _validate_active_plan(plan, timezone.now())
    payload = {"plan_id": plan.public_id, "effective_mode": effective_mode}
    idem, replay = begin_idempotency(
        scope_type="office_subscription_change", scope_id=context.office.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionChangeRequest.objects.get(public_id=replay["request_id"])
    if current.plan_id == plan.id:
        raise DomainAPIException("VALIDATION_ERROR", details={"reason": "same_subscription_plan"})
    existing = SubscriptionChangeRequest.objects.filter(
        office=context.office, status=SubscriptionChangeRequest.Status.PENDING
    ).first()
    if existing is not None:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED", details={"reason": "pending_change_exists"})
    change = SubscriptionChangeRequest.objects.create(
        office=context.office,
        current_subscription=current,
        requested_plan=plan,
        effective_mode=effective_mode,
        requested_by=actor,
    )
    record_audit(
        action="office.subscription.change_requested",
        object_type="subscription_change_request",
        object_id=change.id,
        actor_user=actor,
        office_id=context.office.id,
        request=request,
        after={"plan_id": plan.public_id, "effective_mode": effective_mode},
    )
    OutboxEvent.objects.create(
        aggregate_type="subscription_change_request",
        aggregate_id=change.id,
        event_type="subscription.change.requested",
        payload={"request_id": change.public_id, "office_id": context.office.public_id},
    )
    complete_idempotency(idem, {"request_id": change.public_id})
    return change


@transaction.atomic
def process_due_subscriptions(*, now: datetime | None = None) -> dict[str, int]:
    current = now or timezone.now()
    counts = {"expired": 0, "renewed": 0, "grace": 0}
    due = list(
        OfficeSubscription.objects.select_for_update()
        .select_related("office", "plan")
        .filter(status__in=[OfficeSubscription.Status.TRIAL, OfficeSubscription.Status.ACTIVE], period_end__lte=current)
        .order_by("period_end")
    )
    for subscription in due:
        if subscription.auto_renew and not subscription.cancel_at_period_end:
            pending = SubscriptionChangeRequest.objects.select_for_update().filter(
                office=subscription.office,
                status=SubscriptionChangeRequest.Status.APPROVED,
                effective_mode=SubscriptionChangeRequest.EffectiveMode.NEXT_PERIOD,
            ).select_related("requested_plan").first()
            renewal_plan = pending.requested_plan if pending is not None else subscription.plan
            subscription.status = OfficeSubscription.Status.EXPIRED
            subscription.save(update_fields=["status"])
            end = period_end_for(renewal_plan, subscription.period_end)
            renewed = OfficeSubscription.objects.create(
                office=subscription.office,
                plan=renewal_plan,
                status=(
                    OfficeSubscription.Status.PAST_DUE
                    if renewal_plan.price_amount > 0
                    else OfficeSubscription.Status.ACTIVE
                ),
                period_start=subscription.period_end,
                period_end=end,
                price_snapshot=_price_snapshot(renewal_plan),
                features_snapshot=dict(renewal_plan.features_json),
                limits_snapshot=dict(renewal_plan.limits_json),
                auto_renew=True,
                source="renewal",
            )
            create_subscription_invoice(renewed)
            if pending is not None:
                pending.status = SubscriptionChangeRequest.Status.APPLIED
                pending.applied_at = current
                pending.save(update_fields=["status", "applied_at"])
            counts["renewed"] += 1
        else:
            subscription.status = OfficeSubscription.Status.EXPIRED
            subscription.save(update_fields=["status"])
            counts["expired"] += 1
        OutboxEvent.objects.create(
            aggregate_type="office_subscription",
            aggregate_id=subscription.id,
            event_type="subscription.period.closed",
            payload={
                "subscription_id": subscription.public_id,
                "office_id": subscription.office.public_id,
                "existing_bookings_preserved": True,
            },
        )
    due_open_invoices = SubscriptionInvoice.objects.filter(
        office_subscription_id=OuterRef("pk"),
        status=SubscriptionInvoice.Status.OPEN,
        due_at__lte=current,
    )
    past_due = list(
        OfficeSubscription.objects.select_for_update()
        .filter(status=OfficeSubscription.Status.PAST_DUE)
        .filter(Exists(due_open_invoices))
    )
    for subscription in past_due:
        subscription.status = OfficeSubscription.Status.GRACE
        subscription.save(update_fields=["status"])
        counts["grace"] += 1
    grace_cutoff = current - timedelta(days=int(getattr(settings, "SUBSCRIPTION_GRACE_DAYS", 7)))
    overdue_grace_invoices = SubscriptionInvoice.objects.filter(
        office_subscription_id=OuterRef("pk"),
        status=SubscriptionInvoice.Status.OPEN,
        due_at__lte=grace_cutoff,
    )
    grace_rows = list(
        OfficeSubscription.objects.select_for_update()
        .filter(status=OfficeSubscription.Status.GRACE)
        .filter(Exists(overdue_grace_invoices))
    )
    for subscription in grace_rows:
        subscription.status = OfficeSubscription.Status.EXPIRED
        subscription.save(update_fields=["status"])
        counts["expired"] += 1
    return counts

@transaction.atomic
def review_change_request(
    *, change: SubscriptionChangeRequest, command: str, actor: User, request: HttpRequest,
    idempotency_key: str, payment_reference: str | None = None, reason: str = ""
) -> SubscriptionChangeRequest:
    require_fresh_mfa(request)
    locked = (
        SubscriptionChangeRequest.objects.select_for_update()
        .select_related("office", "requested_plan", "current_subscription")
        .get(id=change.id)
    )
    payload = {"command": command, "payment_reference": payment_reference, "reason": reason}
    idem, replay = begin_idempotency(
        scope_type="subscription_change_review", scope_id=locked.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionChangeRequest.objects.get(public_id=replay["request_id"])
    if locked.status != SubscriptionChangeRequest.Status.PENDING:
        raise DomainAPIException("STATE_TRANSITION_NOT_ALLOWED")
    now = timezone.now()
    if command == "reject":
        locked.status = SubscriptionChangeRequest.Status.REJECTED
        locked.reviewed_by = actor
        locked.reason = reason
        locked.decided_at = now
        locked.save(update_fields=["status", "reviewed_by", "reason", "decided_at"])
    elif command == "approve":
        locked.reviewed_by = actor
        locked.reason = reason
        locked.decided_at = now
        if locked.effective_mode == SubscriptionChangeRequest.EffectiveMode.IMMEDIATE:
            assign_subscription(
                office=locked.office,
                plan=locked.requested_plan,
                actor=actor,
                request=request,
                idempotency_key=f"{idempotency_key}:assign",
                requested_status=OfficeSubscription.Status.ACTIVE,
                auto_renew=bool(locked.current_subscription and locked.current_subscription.auto_renew),
                payment_reference=payment_reference,
                source="change_request",
            )
            locked.status = SubscriptionChangeRequest.Status.APPLIED
            locked.applied_at = now
            locked.save(update_fields=["status", "reviewed_by", "reason", "decided_at", "applied_at"])
        else:
            locked.status = SubscriptionChangeRequest.Status.APPROVED
            locked.save(update_fields=["status", "reviewed_by", "reason", "decided_at"])
    else:
        raise DomainAPIException("VALIDATION_ERROR")
    record_audit(
        action=f"platform.subscription.change.{command}",
        object_type="subscription_change_request",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        before={"status": SubscriptionChangeRequest.Status.PENDING},
        after={"status": locked.status, "reason": reason},
    )
    complete_idempotency(idem, {"request_id": locked.public_id})
    return locked


@transaction.atomic
def close_invoice(
    *, invoice: SubscriptionInvoice, command: str, actor: User, request: HttpRequest,
    idempotency_key: str, reason: str
) -> SubscriptionInvoice:
    require_fresh_mfa(request)
    locked = (
        SubscriptionInvoice.objects.select_for_update()
        .select_related("office", "office_subscription")
        .get(id=invoice.id)
    )
    payload = {"command": command, "reason": reason}
    idem, replay = begin_idempotency(
        scope_type="subscription_invoice_close", scope_id=locked.id, key=idempotency_key, payload=payload
    )
    if replay is not None:
        return SubscriptionInvoice.objects.get(public_id=replay["invoice_id"])
    if locked.status != SubscriptionInvoice.Status.OPEN:
        raise DomainAPIException("PAYMENT_STATE_CONFLICT")
    if command not in {"void", "mark_uncollectible"}:
        raise DomainAPIException("VALIDATION_ERROR")
    if locked.ledger_entry is not None:
        reversal = post_ledger_entry(
            event_type="SUBSCRIPTION_CREDIT_NOTE",
            event_id=locked.id,
            office=locked.office,
            currency=locked.currency,
            occurred_at=timezone.now(),
            description=f"Reverse subscription invoice {locked.public_id}: {reason}",
            reversal_of=locked.ledger_entry,
            status="reversed",
            postings=[
                PostingSpec(
                    account_code="4010_SUBSCRIPTION_REVENUE",
                    account_type=LedgerAccount.AccountType.REVENUE,
                    direction=LedgerPosting.Direction.DEBIT,
                    amount=locked.total_amount,
                ),
                PostingSpec(
                    account_code="1030_OTHER_RECEIVABLE",
                    account_type=LedgerAccount.AccountType.ASSET,
                    direction=LedgerPosting.Direction.CREDIT,
                    amount=locked.total_amount,
                    office_scoped=True,
                ),
            ],
        )
        locked.ledger_entry.status = "reversed"
        locked.ledger_entry.save(update_fields=["status"])
        del reversal
    locked.status = (
        SubscriptionInvoice.Status.VOID if command == "void" else SubscriptionInvoice.Status.UNCOLLECTIBLE
    )
    locked.save(update_fields=["status"])
    record_audit(
        action=f"platform.subscription.invoice.{command}",
        object_type="subscription_invoice",
        object_id=locked.id,
        actor_user=actor,
        office_id=locked.office_id,
        request=request,
        after={"status": locked.status, "reason": reason},
    )
    complete_idempotency(idem, {"invoice_id": locked.public_id})
    return locked
