from __future__ import annotations

from rest_framework import serializers

from support.models import SupportCase, SupportMessage


class SupportCaseSerializer(serializers.ModelSerializer[SupportCase]):
    id = serializers.CharField(source="public_id")
    booking_id = serializers.CharField(source="booking.public_id", allow_null=True, read_only=True)
    trip_id = serializers.CharField(source="trip.public_id", allow_null=True, read_only=True)
    office_id = serializers.CharField(source="office.public_id", allow_null=True, read_only=True)

    class Meta:
        model = SupportCase
        fields = [
            "id",
            "priority",
            "category",
            "status",
            "booking_id",
            "trip_id",
            "office_id",
            "sla_due_at",
            "opened_at",
            "resolution_code",
            "metadata",
        ]


class SupportMessageSerializer(serializers.ModelSerializer[SupportMessage]):
    sender_user_id = serializers.CharField(source="sender_user.public_id", allow_null=True, read_only=True)

    class Meta:
        model = SupportMessage
        fields = ["id", "sender_type", "sender_user_id", "body", "visibility", "created_at"]


class GuestSupportCaseRequestSerializer(serializers.Serializer[dict[str, object]]):
    category = serializers.CharField(max_length=60)
    priority = serializers.ChoiceField(choices=SupportCase.Priority.choices)
    message = serializers.CharField(max_length=4000)
    attachments = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class SupportMessageRequestSerializer(serializers.Serializer[dict[str, object]]):
    body = serializers.CharField(max_length=4000)
    visibility = serializers.ChoiceField(
        choices=SupportMessage.Visibility.choices,
        required=False,
        default=SupportMessage.Visibility.SHARED,
    )
    file_ids = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class SupportCaseCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["assign", "resolve", "close", "reopen"])
    resolution_code = serializers.CharField(max_length=80, required=False, allow_blank=True)
