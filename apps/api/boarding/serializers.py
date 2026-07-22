from typing import Any

from rest_framework import serializers


class BoardingCommandSerializer(serializers.Serializer[dict[str, Any]]):
    command = serializers.ChoiceField(choices=["arrive", "verify", "board", "reverse", "deny", "no_show"])
    ticket_qr = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    passenger_id = serializers.UUIDField(required=False, allow_null=True)
    reason_code = serializers.CharField(required=False, allow_null=True, allow_blank=False, max_length=80)
    offline_event_id = serializers.CharField(required=False, allow_null=True, allow_blank=False, max_length=80)
    occurred_at = serializers.DateTimeField(required=False)
    correction_approval_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        if not attrs.get("ticket_qr") and not attrs.get("passenger_id"):
            raise serializers.ValidationError("ticket_qr_or_passenger_id_required")
        return attrs


class OfflineSyncSerializer(serializers.Serializer[dict[str, Any]]):
    package_hash = serializers.CharField(min_length=64, max_length=64)
    events = BoardingCommandSerializer(many=True)


class OfflinePackageResponseSerializer(serializers.Serializer[dict[str, Any]]):
    download_url = serializers.CharField()
    expires_at = serializers.DateTimeField()
    package_hash = serializers.CharField()


class BoardingResultSerializer(serializers.Serializer[dict[str, Any]]):
    passenger_id = serializers.UUIDField()
    boarding_status = serializers.CharField()
    ticket_status = serializers.CharField(allow_null=True)


class OfflineSyncResponseSerializer(serializers.Serializer[dict[str, Any]]):
    accepted = serializers.IntegerField()
    duplicates = serializers.IntegerField()
    conflicts = serializers.ListField(child=serializers.DictField())
    purge_required = serializers.BooleanField()
