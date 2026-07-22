from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

from trips.models import Trip

ZERO = Decimal("0.00")


def _money(value: object, *, default: Decimal = ZERO) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return default


def base_unit_price(trip: Trip) -> Decimal:
    snapshot_value = trip.pricing_snapshot.get("base_price")
    return _money(snapshot_value, default=trip.base_price)


def unit_fee(trip: Trip) -> Decimal:
    return _money(trip.pricing_snapshot.get("fee_per_passenger"))


def fixed_fee(trip: Trip) -> Decimal:
    return _money(trip.pricing_snapshot.get("fixed_fee"))


def unit_discount(trip: Trip) -> Decimal:
    return _money(trip.pricing_snapshot.get("discount_per_passenger"))


def honest_from_price(trip: Trip) -> Decimal:
    return max(ZERO, base_unit_price(trip) - unit_discount(trip) + unit_fee(trip) + fixed_fee(trip))


def payment_methods(trip: Trip) -> list[str]:
    methods = trip.pricing_snapshot.get("payment_methods", [])
    return [str(item) for item in methods] if isinstance(methods, list) else []


def cancellation_summary(trip: Trip) -> str:
    policy = trip.policy_snapshot.get("cancellation", {})
    if not isinstance(policy, dict):
        return ""
    rules = policy.get("rules", {})
    if isinstance(rules, dict) and rules.get("summary"):
        return str(rules["summary"])
    return str(policy.get("title", ""))


def policy_version_ids(trip: Trip) -> list[str]:
    identifiers: list[str] = []
    for value in trip.policy_snapshot.values():
        if isinstance(value, dict) and value.get("id"):
            identifiers.append(str(value["id"]))
    return sorted(set(identifiers))


def payment_deadline_minutes(trip: Trip) -> int:
    raw = trip.pricing_snapshot.get("payment_deadline_minutes")
    if raw in (None, ""):
        payment_policy = trip.policy_snapshot.get("payment", {})
        if isinstance(payment_policy, dict):
            rules = payment_policy.get("rules", {})
            if isinstance(rules, dict):
                raw = rules.get("payment_deadline_minutes") or rules.get("deadline_minutes")
    try:
        minutes = int(str(raw)) if raw not in (None, "") else 30
    except (TypeError, ValueError):
        minutes = 30
    return min(max(minutes, 5), 24 * 60)


def booking_quote(trip: Trip, *, passenger_count: int) -> dict[str, Any]:
    count = Decimal(passenger_count)
    subtotal = (base_unit_price(trip) * count).quantize(Decimal("0.01"))
    discount = (unit_discount(trip) * count).quantize(Decimal("0.01"))
    fees = (unit_fee(trip) * count + fixed_fee(trip)).quantize(Decimal("0.01"))
    total = max(ZERO, subtotal - discount + fees).quantize(Decimal("0.01"))
    payment_deadline_at = timezone.now() + timedelta(minutes=payment_deadline_minutes(trip))
    return {
        "subtotal": {"amount": str(subtotal), "currency": trip.currency},
        "discount": {"amount": str(discount), "currency": trip.currency},
        "fees": {"amount": str(fees), "currency": trip.currency},
        "total": {"amount": str(total), "currency": trip.currency},
        "payment_deadline_at": payment_deadline_at,
        "policy_version_ids": policy_version_ids(trip),
        "quote_version": trip.version,
    }
