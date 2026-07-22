from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from adminops.models import OfficeStatusAction, PlatformActionApproval
from organizations.models import Office
from support.models import OfficeViolation


class OfficeViolationSerializer(serializers.ModelSerializer[OfficeViolation]):
    office_id = serializers.CharField(source="office.public_id", read_only=True)
    support_case_id = serializers.CharField(source="support_case.public_id", read_only=True)
    description = serializers.SerializerMethodField()
    evidence = serializers.SerializerMethodField()

    class Meta:
        model = OfficeViolation
        fields = [
            "id",
            "office_id",
            "support_case_id",
            "code",
            "severity",
            "status",
            "description",
            "evidence",
            "created_at",
            "closed_at",
        ]

    def get_description(self, obj: OfficeViolation) -> str:
        return str(obj.details.get("description", ""))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_evidence(self, obj: OfficeViolation) -> dict[str, object]:
        value = obj.details.get("evidence", {})
        return value if isinstance(value, dict) else {}


class OfficeViolationWriteSerializer(serializers.Serializer[dict[str, object]]):
    code = serializers.CharField(max_length=80)
    severity = serializers.ChoiceField(choices=["P0", "P1", "P2", "P3", "P4"])
    description = serializers.CharField(min_length=10, max_length=4000)
    evidence = serializers.JSONField(required=False, default=dict)


class OfficeViolationCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["acknowledge", "close"])
    reason = serializers.CharField(min_length=10, max_length=1000)


class OfficeStatusCommandSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(
        choices=[
            Office.Status.ACTIVE,
            Office.Status.RESTRICTED,
            Office.Status.NO_NEW_BOOKINGS,
            Office.Status.SUSPENDED,
            Office.Status.TERMINATED,
        ]
    )
    reason = serializers.CharField(min_length=10, max_length=1000)


class OfficeStatusActionSerializer(serializers.ModelSerializer[OfficeStatusAction]):
    actor_id = serializers.CharField(source="actor.public_id", read_only=True)

    class Meta:
        model = OfficeStatusAction
        fields = ["id", "previous_status", "new_status", "reason", "actor_id", "created_at"]


class PlatformApprovalSerializer(serializers.ModelSerializer[PlatformActionApproval]):
    requested_by = serializers.CharField(source="requested_by.public_id", read_only=True)
    approved_by = serializers.CharField(source="approved_by.public_id", read_only=True, allow_null=True)

    class Meta:
        model = PlatformActionApproval
        fields = [
            "public_id",
            "action_type",
            "target_type",
            "target_id",
            "payload",
            "risk_level",
            "status",
            "reason",
            "requested_by",
            "approved_by",
            "requested_at",
            "approved_at",
            "executed_at",
        ]


class PlatformApprovalCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(min_length=10, max_length=1000)
