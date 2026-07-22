from __future__ import annotations

from rest_framework import serializers


class PaymentIntentSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    method_type = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    provider_action = serializers.JSONField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)


class CreatePaymentIntentSerializer(serializers.Serializer[dict[str, object]]):
    method_type = serializers.ChoiceField(
        choices=[
            ("office_cash", "Office cash"),
            ("manual_transfer", "Manual transfer"),
            ("electronic", "Electronic"),
        ]
    )
    return_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)


class ManualTransferSerializer(serializers.Serializer[dict[str, object]]):
    transfer_reference = serializers.CharField(max_length=160)
    transferred_at = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    sender_reference = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=160)
    proof_file_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=500)


class OfficeCashPaymentSerializer(serializers.Serializer[dict[str, object]]):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    receipt_number = serializers.CharField(min_length=3, max_length=120)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)


class ManualPaymentDecisionSerializer(serializers.Serializer[dict[str, object]]):
    decision = serializers.ChoiceField(choices=["verify", "reject"])
    reason = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=1000)


class ManualPaymentQueueItemSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    booking_id = serializers.CharField()
    pnr = serializers.CharField()
    transfer_reference = serializers.CharField()
    sender_reference = serializers.CharField(allow_null=True)
    transferred_at = serializers.DateTimeField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    proof_file_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    submitted_at = serializers.DateTimeField()


class PaymentWebhookRequestSerializer(serializers.Serializer[dict[str, object]]):
    event_id = serializers.CharField(max_length=160)
    intent_id = serializers.CharField(max_length=26)
    status = serializers.ChoiceField(choices=["succeeded"])
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField(min_length=3, max_length=3)
    occurred_at = serializers.DateTimeField()
    provider_reference = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=160)


class WebhookResponseSerializer(serializers.Serializer[dict[str, object]]):
    received = serializers.BooleanField()


class RefundSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    booking_id = serializers.CharField()
    pnr = serializers.CharField()
    passenger_id = serializers.UUIDField(allow_null=True)
    passenger_name = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    requested_amount = serializers.CharField()
    approved_amount = serializers.CharField(allow_null=True)
    currency = serializers.CharField()
    reason_code = serializers.CharField()
    provider_reference = serializers.CharField(allow_null=True)
    requested_by = serializers.UUIDField(allow_null=True)
    approved_by = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)


class RefundCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(
        choices=["review", "approve", "reject", "process", "succeed", "fail", "retry", "cancel"]
    )
    approved_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    provider_reference = serializers.CharField(required=False, allow_blank=True, max_length=160)


class ChargebackSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    provider_case_id = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.CharField()
    currency = serializers.CharField()
    booking_id = serializers.CharField()
    opened_at = serializers.DateTimeField()
    deadline_at = serializers.DateTimeField(allow_null=True)
