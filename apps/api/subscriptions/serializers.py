from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from subscriptions.models import OfficeSubscription, SubscriptionChangeRequest, SubscriptionPlan


class SubscriptionMoneySerializer(serializers.Serializer[dict[str, object]]):
    amount = serializers.CharField()
    currency = serializers.CharField()


class SubscriptionPlanSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField(required=False)
    code = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=160)
    billing_period = serializers.ChoiceField(choices=SubscriptionPlan.BillingPeriod.choices)
    price = SubscriptionMoneySerializer(required=False)
    price_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, min_value=Decimal("0"))
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    features = serializers.JSONField(required=False, default=dict)
    limits = serializers.JSONField(required=False, default=dict)
    status = serializers.ChoiceField(choices=SubscriptionPlan.Status.choices, required=False)
    effective_from = serializers.DateTimeField(required=False)
    effective_to = serializers.DateTimeField(required=False, allow_null=True)
    version = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        price = attrs.pop("price", None)
        if isinstance(price, dict):
            attrs.setdefault("price_amount", price.get("amount"))
            attrs.setdefault("currency", price.get("currency"))
        if self.instance is None:
            required = ["price_amount", "currency"]
            missing = [field for field in required if field not in attrs]
            if missing:
                raise serializers.ValidationError({field: "required" for field in missing})
        return attrs


class SubscriptionPlanPatchSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=160, required=False)
    billing_period = serializers.ChoiceField(choices=SubscriptionPlan.BillingPeriod.choices, required=False)
    price_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, min_value=Decimal("0"))
    currency = serializers.CharField(min_length=3, max_length=3, required=False)
    features = serializers.JSONField(required=False)
    limits = serializers.JSONField(required=False)
    status = serializers.ChoiceField(choices=SubscriptionPlan.Status.choices, required=False)
    effective_from = serializers.DateTimeField(required=False)
    effective_to = serializers.DateTimeField(required=False, allow_null=True)
    version = serializers.IntegerField(min_value=1)


class OfficeSubscriptionSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    office_id = serializers.CharField(required=False)
    plan = SubscriptionPlanSerializer()
    status = serializers.CharField()
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    price_snapshot = serializers.JSONField(required=False)
    features = serializers.JSONField(required=False)
    limits = serializers.JSONField(required=False)
    usage = serializers.JSONField(required=False)
    access_mode = serializers.CharField(required=False)
    auto_renew = serializers.BooleanField()
    cancel_at_period_end = serializers.BooleanField()
    invoices = serializers.JSONField(required=False)


class SetOfficeSubscriptionSerializer(serializers.Serializer[dict[str, object]]):
    plan_id = serializers.CharField(max_length=26)
    status = serializers.ChoiceField(
        choices=[OfficeSubscription.Status.TRIAL, OfficeSubscription.Status.ACTIVE],
        required=False,
        default=OfficeSubscription.Status.ACTIVE,
    )
    period_start = serializers.DateTimeField(required=False)
    period_end = serializers.DateTimeField(required=False)
    auto_renew = serializers.BooleanField(required=False, default=False)
    payment_reference = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=160)


class SubscriptionChangeRequestWriteSerializer(serializers.Serializer[dict[str, object]]):
    plan_id = serializers.CharField(max_length=26)
    effective_mode = serializers.ChoiceField(choices=SubscriptionChangeRequest.EffectiveMode.choices)


class SubscriptionChangeRequestSerializer(serializers.Serializer[dict[str, object]]):
    request_id = serializers.CharField()
    status = serializers.CharField()
    plan_id = serializers.CharField()
    effective_mode = serializers.CharField()
    requested_at = serializers.DateTimeField()


class InvoicePaymentSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["mark_paid", "void", "mark_uncollectible"])
    payment_reference = serializers.CharField(required=False, allow_blank=True, max_length=160)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
