from __future__ import annotations

from typing import Any

from rest_framework import serializers

from policies.models import ConfigurationValue, PolicyTemplate, PolicyVersion


class PolicyVersionSerializer(serializers.ModelSerializer[PolicyVersion]):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(source="template.code", read_only=True)
    policy_type = serializers.CharField(source="template.policy_type", read_only=True)
    owner_scope = serializers.CharField(source="template.owner_scope", read_only=True)
    office_id = serializers.CharField(source="office.public_id", read_only=True, allow_null=True)

    class Meta:
        model = PolicyVersion
        fields = [
            "id",
            "code",
            "policy_type",
            "owner_scope",
            "office_id",
            "version_no",
            "language",
            "title",
            "content_markdown",
            "rules_json",
            "effective_from",
            "effective_to",
            "published_at",
            "content_sha256",
        ]


class PolicyVersionWriteSerializer(serializers.Serializer[dict[str, object]]):
    template_code = serializers.CharField(max_length=80, required=False)
    code = serializers.CharField(max_length=80, required=False, write_only=True)
    policy_type = serializers.ChoiceField(choices=PolicyTemplate.PolicyType.choices)
    owner_scope = serializers.ChoiceField(choices=PolicyTemplate.OwnerScope.choices)
    office_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    language = serializers.CharField(max_length=5, default="ar")
    title = serializers.CharField(max_length=200)
    content_markdown = serializers.CharField()
    rules_json = serializers.JSONField(default=dict)
    effective_from = serializers.DateTimeField()
    effective_to = serializers.DateTimeField(required=False, allow_null=True)
    publish = serializers.BooleanField(default=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        code = str(attrs.get("template_code") or attrs.get("code") or "").strip()
        if not code:
            raise serializers.ValidationError({"template_code": "required"})
        attrs["code"] = code
        attrs.pop("template_code", None)
        return attrs


class ConfigurationChangeSerializer(serializers.ModelSerializer[ConfigurationValue]):
    id = serializers.UUIDField(read_only=True)
    created_by = serializers.UUIDField(source="created_by_id", read_only=True)
    approved_by = serializers.UUIDField(source="approved_by_id", read_only=True, allow_null=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = ConfigurationValue
        fields = [
            "id",
            "scope_type",
            "scope_id",
            "key",
            "value_json",
            "value_type",
            "effective_from",
            "effective_to",
            "created_by",
            "approved_by",
            "created_at",
            "reason",
            "status",
        ]

    def get_status(self, obj: ConfigurationValue) -> str:
        return "approved" if obj.approved_by_id is not None else "pending_approval"


class ConfigurationPatchSerializer(serializers.Serializer[dict[str, object]]):
    action = serializers.ChoiceField(choices=["propose", "approve"], default="propose")
    changes = serializers.DictField(child=serializers.JSONField(), required=False)
    change_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    reason = serializers.CharField(min_length=3, max_length=240)
    effective_from = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        action = str(attrs.get("action", "propose"))
        if action == "propose" and not attrs.get("changes"):
            raise serializers.ValidationError({"changes": "required"})
        if action == "approve" and not attrs.get("change_ids"):
            raise serializers.ValidationError({"change_ids": "required"})
        return attrs


class ConfigurationResponseSerializer(serializers.Serializer[dict[str, Any]]):
    effective = serializers.DictField(child=serializers.JSONField())
    pending_changes = ConfigurationChangeSerializer(many=True)
