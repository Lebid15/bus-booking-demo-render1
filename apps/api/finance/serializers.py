from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class SettlementSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    office_id = serializers.CharField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    currency = serializers.CharField()
    status = serializers.CharField()
    gross_amount = serializers.CharField()
    commission_amount = serializers.CharField()
    refund_amount = serializers.CharField()
    reserve_amount = serializers.CharField()
    adjustment_amount = serializers.CharField()
    net_amount = serializers.CharField()
    created_by = serializers.UUIDField()
    approved_by = serializers.UUIDField(allow_null=True)
    payment_reference = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    paid_at = serializers.DateTimeField(allow_null=True)
    items = serializers.ListField(child=serializers.DictField(), required=False)


class CreateSettlementSerializer(serializers.Serializer[dict[str, object]]):
    office_id = serializers.CharField(max_length=26)
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    currency = serializers.CharField(min_length=3, max_length=3)


class SettlementCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(
        choices=["calculate", "submit_review", "approve", "process", "mark_paid", "retry", "close"]
    )
    payment_reference = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=160)


class CommissionProfileSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField(required=False)
    code = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=160)
    calculation_type = serializers.ChoiceField(choices=["percentage", "fixed", "hybrid"])
    percentage_rate = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, default=Decimal("0"))
    fixed_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0"))
    currency = serializers.CharField(min_length=3, max_length=3, required=False, allow_null=True, allow_blank=True)
    status = serializers.CharField(required=False, default="draft", max_length=20)
    version = serializers.IntegerField(required=False)
    effective_from = serializers.DateTimeField(required=False, allow_null=True)


class CommissionProfilePatchSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=160, required=False)
    calculation_type = serializers.ChoiceField(choices=["percentage", "fixed", "hybrid"], required=False)
    percentage_rate = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    fixed_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    currency = serializers.CharField(min_length=3, max_length=3, required=False, allow_null=True, allow_blank=True)
    status = serializers.CharField(required=False, max_length=20)
    version = serializers.IntegerField()
    effective_from = serializers.DateTimeField(required=False, allow_null=True)


class FinancialEffectSerializer(serializers.Serializer[dict[str, object]]):
    type = serializers.ChoiceField(choices=["none", "office_credit", "office_debit", "customer_compensation"])
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0"))


class DisputeCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["assign_office", "decide", "decide_appeal", "close_no_appeal"])
    decision_code = serializers.CharField(required=False, max_length=80)
    reasoning = serializers.CharField(required=False, max_length=4000)
    financial_effect = FinancialEffectSerializer(required=False)


class OfficeDisputeResponseSerializer(serializers.Serializer[dict[str, object]]):
    response = serializers.CharField(min_length=10, max_length=4000)
    evidence = serializers.JSONField()


class DisputeAppealSerializer(serializers.Serializer[dict[str, object]]):
    reason = serializers.CharField(min_length=10, max_length=4000)
    evidence = serializers.JSONField(required=False, default=dict)
