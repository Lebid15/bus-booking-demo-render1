from __future__ import annotations

from typing import Any

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from identity.models import UserSession


class RegisterSerializer(serializers.Serializer[dict[str, Any]]):
    full_name = serializers.CharField(max_length=160)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    phone = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=30)
    password = serializers.CharField(write_only=True, min_length=10, max_length=128)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs):  # type: ignore[no-untyped-def]
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError({"identifier": "email_or_phone_required"})
        return attrs


class RegistrationVerifySerializer(serializers.Serializer[dict[str, Any]]):
    challenge_id = serializers.CharField(max_length=100)
    code = serializers.RegexField(r"^\d{6}$")


class LoginSerializer(serializers.Serializer[dict[str, Any]]):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, max_length=128)


class MfaVerifySerializer(serializers.Serializer[dict[str, Any]]):
    challenge_id = serializers.CharField(max_length=100)
    code = serializers.RegexField(r"^\d{6,8}$")


class SessionSerializer(serializers.ModelSerializer[UserSession]):
    device = serializers.SerializerMethodField()
    current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = ["id", "device", "user_agent", "created_at", "expires_at", "revoked_at", "current"]

    def get_device(self, obj: UserSession) -> dict[str, Any] | None:
        if obj.device is None:
            return None
        return {
            "id": str(obj.device_id),
            "label": obj.device.label,
            "trusted_at": obj.device.trusted_at,
            "last_seen_at": obj.device.last_seen_at,
        }

    def get_current(self, obj: UserSession) -> bool:
        current = self.context.get("current_session")
        return bool(current and current.id == obj.id)
