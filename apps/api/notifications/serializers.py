from __future__ import annotations

from rest_framework import serializers

from notifications.models import Notification, NotificationDelivery, NotificationPreference, PushSubscription


class NotificationDeliverySerializer(serializers.ModelSerializer[NotificationDelivery]):
    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "channel",
            "status",
            "attempt_no",
            "provider_message_id",
            "next_attempt_at",
            "sent_at",
            "delivered_at",
            "error_code",
            "permanent_failure",
        ]


class NotificationSerializer(serializers.ModelSerializer[Notification]):
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_version = serializers.IntegerField(source="template.version", read_only=True)
    channel = serializers.CharField(source="template.channel", read_only=True)
    booking_id = serializers.CharField(source="booking.public_id", allow_null=True, read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "event_type",
            "recipient_type",
            "booking_id",
            "template_code",
            "template_version",
            "channel",
            "language",
            "rendered_subject",
            "rendered_body",
            "status",
            "action_required",
            "action_url",
            "read_at",
            "created_at",
        ]


class NotificationPreferenceSerializer(serializers.ModelSerializer[NotificationPreference]):
    class Meta:
        model = NotificationPreference
        fields = ["event_type", "channel", "enabled", "updated_at"]
        read_only_fields = ["updated_at"]


class NotificationPreferenceBulkSerializer(serializers.Serializer[dict[str, object]]):
    preferences = NotificationPreferenceSerializer(many=True)


class PushSubscriptionWriteSerializer(serializers.Serializer[dict[str, object]]):
    token = serializers.CharField(min_length=16, max_length=4096, write_only=True)
    platform = serializers.ChoiceField(choices=["android", "ios", "web"])


class PushSubscriptionSerializer(serializers.ModelSerializer[PushSubscription]):
    class Meta:
        model = PushSubscription
        fields = ["id", "platform", "status", "created_at", "revoked_at"]
