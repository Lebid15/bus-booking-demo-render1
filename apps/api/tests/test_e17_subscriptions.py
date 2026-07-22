from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import RequestFactory, override_settings
from django.utils import timezone

from common.exceptions import DomainAPIException
from finance.services import assert_entry_balanced
from identity.models import UserSession
from subscriptions.models import OfficeSubscription, SubscriptionInvoice, SubscriptionPlan
from subscriptions.services import (
    assign_subscription,
    commercial_access,
    process_due_subscriptions,
    update_plan,
)
from trips.public_services import assert_public_bookable

from .test_e13_policies_configuration import _confirmed_booking

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _plan(*, price: str = "100.00", code: str | None = None) -> SubscriptionPlan:
    return SubscriptionPlan.objects.create(
        code=code or f"plan-{uuid.uuid4().hex[:8]}",
        name_ar="الباقة الاحترافية",
        billing_period=SubscriptionPlan.BillingPeriod.MONTHLY,
        price_amount=Decimal(price),
        currency="SYP",
        features_json={"public_booking": True, "reports": True},
        limits_json={"max_branches": 3, "max_staff": 10, "max_vehicles": 8, "max_monthly_trips": 100},
        status=SubscriptionPlan.Status.ACTIVE,
        effective_from=timezone.now() - timedelta(days=1),
    )


def _mfa_request(actor, key: str):  # type: ignore[no-untyped-def]
    request = RequestFactory().patch(
        "/v1/platform/subscription-plans/test",
        HTTP_IDEMPOTENCY_KEY=key,
        REMOTE_ADDR="203.0.113.17",
    )
    request.user = actor
    request.auth = UserSession.objects.create(
        user=actor,
        token_hash=f"e17-{uuid.uuid4()}".encode(),
        expires_at=timezone.now() + timedelta(hours=2),
        mfa_verified_at=timezone.now(),
    )
    return request


@override_settings(SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_e17_ac01_assignment_saves_plan_price_features_limits_and_period_snapshot() -> None:
    booking, _ = _confirmed_booking()
    plan = _plan(price="1250.00")
    start = timezone.now()

    subscription = assign_subscription(
        office=booking.office,
        plan=plan,
        actor=booking.trip.created_by,
        request=None,
        idempotency_key="e17-ac01-subscribe",
        requested_status=OfficeSubscription.Status.ACTIVE,
        period_start=start,
        auto_renew=True,
        payment_reference="SUB-PAY-AC01",
    )

    assert subscription.plan_id == plan.id
    assert subscription.price_snapshot["amount"] == "1250.00"
    assert subscription.price_snapshot["plan_version"] == 1
    assert subscription.features_snapshot == plan.features_json
    assert subscription.limits_snapshot == plan.limits_json
    assert subscription.period_start == start
    assert subscription.period_end > start
    assert subscription.status == OfficeSubscription.Status.ACTIVE


@override_settings(SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_e17_ac02_expiry_preserves_existing_booking_and_restricts_new_sales() -> None:
    booking, _ = _confirmed_booking()
    plan = _plan(price="0.00")
    now = timezone.now()
    subscription = OfficeSubscription.objects.create(
        office=booking.office,
        plan=plan,
        status=OfficeSubscription.Status.ACTIVE,
        period_start=now - timedelta(days=31),
        period_end=now - timedelta(seconds=1),
        price_snapshot={
            "plan_id": plan.public_id,
            "plan_code": plan.code,
            "plan_version": plan.version,
            "amount": "0.00",
            "currency": "SYP",
            "billing_period": "monthly",
        },
        features_snapshot=plan.features_json,
        limits_snapshot=plan.limits_json,
        auto_renew=False,
    )

    result = process_due_subscriptions(now=now)

    subscription.refresh_from_db()
    booking.refresh_from_db()
    assert result["expired"] == 1
    assert subscription.status == OfficeSubscription.Status.EXPIRED
    assert booking.pk is not None
    assert booking.status != "cancelled"
    assert commercial_access(booking.office, now=now)["mode"] == "existing_bookings_only"
    with pytest.raises(DomainAPIException) as exc:
        assert_public_bookable(booking.trip, now=now)
    assert exc.value.code == "TRIP_NOT_BOOKABLE"


@override_settings(SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_e17_ac03_paid_invoice_posts_balanced_invoiced_and_paid_entries() -> None:
    booking, _ = _confirmed_booking()
    plan = _plan(price="2500.00")

    subscription = assign_subscription(
        office=booking.office,
        plan=plan,
        actor=booking.trip.created_by,
        request=None,
        idempotency_key="e17-ac03-subscribe",
        requested_status=OfficeSubscription.Status.ACTIVE,
        auto_renew=False,
        payment_reference="SUBSCRIPTION-RECEIPT-AC03",
    )

    invoice = SubscriptionInvoice.objects.get(office_subscription=subscription)
    assert invoice.status == SubscriptionInvoice.Status.PAID
    assert invoice.ledger_entry is not None
    assert invoice.payment_ledger_entry is not None
    assert invoice.ledger_entry.event_type == "SUBSCRIPTION_INVOICED"
    assert invoice.payment_ledger_entry.event_type == "SUBSCRIPTION_PAID"
    assert_entry_balanced(invoice.ledger_entry)
    assert_entry_balanced(invoice.payment_ledger_entry)


@override_settings(SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_e17_ac04_plan_price_change_does_not_rewrite_paid_period_snapshot() -> None:
    booking, _ = _confirmed_booking()
    plan = _plan(price="1000.00")
    subscription = assign_subscription(
        office=booking.office,
        plan=plan,
        actor=booking.trip.created_by,
        request=None,
        idempotency_key="e17-ac04-subscribe",
        requested_status=OfficeSubscription.Status.ACTIVE,
        payment_reference="SUBSCRIPTION-RECEIPT-AC04",
    )
    request = _mfa_request(booking.trip.created_by, "e17-ac04-plan-update")

    update_plan(
        plan=plan,
        actor=booking.trip.created_by,
        request=request,
        data={"price_amount": Decimal("1800.00"), "version": 1},
        idempotency_key="e17-ac04-plan-update",
    )

    plan.refresh_from_db()
    subscription.refresh_from_db()
    assert plan.price_amount == Decimal("1800.00")
    assert subscription.price_snapshot["amount"] == "1000.00"
    assert subscription.price_snapshot["plan_version"] == 1


@override_settings(SUBSCRIPTION_ENFORCEMENT_ENABLED=True)
def test_trial_is_one_time_per_office() -> None:
    booking, _ = _confirmed_booking()
    plan = _plan(price="0.00")
    first = assign_subscription(
        office=booking.office,
        plan=plan,
        actor=booking.trip.created_by,
        request=None,
        idempotency_key="e17-trial-first",
        requested_status=OfficeSubscription.Status.TRIAL,
    )
    first.status = OfficeSubscription.Status.EXPIRED
    first.save(update_fields=["status"])

    with pytest.raises(DomainAPIException) as exc:
        assign_subscription(
            office=booking.office,
            plan=plan,
            actor=booking.trip.created_by,
            request=None,
            idempotency_key="e17-trial-second",
            requested_status=OfficeSubscription.Status.TRIAL,
        )
    assert exc.value.code == "SUBSCRIPTION_TRIAL_ALREADY_USED"
