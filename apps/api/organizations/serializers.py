from __future__ import annotations

from typing import Any, cast

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from geography.serializers import LocationSerializer
from organizations.models import (
    Office,
    OfficeBranch,
    OfficeDocument,
    OfficeMembership,
    OfficePayoutAccount,
    VerificationCase,
)


class OfficeBranchSerializer(serializers.ModelSerializer[OfficeBranch]):
    id = serializers.CharField(source="public_id")
    location = LocationSerializer()

    class Meta:
        model = OfficeBranch
        fields = ["id", "name", "phone", "status", "is_primary", "version", "location"]


class OfficeBranchWriteSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=160, required=False)
    location_id = serializers.CharField(required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    status = serializers.ChoiceField(choices=["active", "inactive", "suspended"], required=False)
    is_primary = serializers.BooleanField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)


class OfficeSerializer(serializers.ModelSerializer[Office]):
    id = serializers.CharField(source="public_id")
    public_id = serializers.CharField(read_only=True)

    class Meta:
        model = Office
        fields = [
            "id",
            "public_id",
            "legal_name",
            "trade_name",
            "office_type",
            "status",
            "timezone",
            "default_currency",
            "support_phone",
            "support_email",
        ]


class OfficeDocumentSerializer(serializers.ModelSerializer[OfficeDocument]):
    class Meta:
        model = OfficeDocument
        fields = [
            "id",
            "document_type",
            "sha256",
            "status",
            "issued_at",
            "expires_at",
            "is_critical",
            "reviewed_at",
        ]


class VerificationCaseSerializer(serializers.ModelSerializer[VerificationCase]):
    documents = serializers.SerializerMethodField()

    class Meta:
        model = VerificationCase
        fields = [
            "id",
            "status",
            "risk_level",
            "submitted_at",
            "decided_at",
            "decision_reason",
            "conditions",
            "version",
            "reviewer_user_id",
            "approver_user_id",
            "documents",
        ]

    @extend_schema_field(OfficeDocumentSerializer(many=True))
    def get_documents(self, obj: VerificationCase) -> list[dict[str, Any]]:
        documents = obj.office.documents.order_by("document_type", "-created_at")
        latest_by_type: dict[str, OfficeDocument] = {}
        for document in documents:
            latest_by_type.setdefault(document.document_type, document)
        serialized = OfficeDocumentSerializer(list(latest_by_type.values()), many=True).data
        return cast(list[dict[str, Any]], list(serialized))


class VerificationCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(
        choices=[
            "submit",
            "start_review",
            "request_info",
            "resubmit",
            "external_check",
            "conditional_approve",
            "approve",
            "reject",
            "expire",
        ]
    )
    reason = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    conditions = serializers.JSONField(required=False, allow_null=True)


class MembershipSerializer(serializers.ModelSerializer[OfficeMembership]):
    id = serializers.UUIDField(read_only=True)
    user = serializers.SerializerMethodField()
    branch_id = serializers.SerializerMethodField()
    role = serializers.CharField(source="role.code")

    class Meta:
        model = OfficeMembership
        fields = ["id", "user", "branch_id", "role", "status"]

    def get_user(self, obj: OfficeMembership) -> dict[str, str | None]:
        return {
            "id": obj.user.public_id,
            "name": obj.user.full_name,
            "phone": obj.user.phone_e164,
            "email": obj.user.email,
        }

    def get_branch_id(self, obj: OfficeMembership) -> str | None:
        return obj.branch.public_id if obj.branch else None


class StaffInviteSerializer(serializers.Serializer[dict[str, object]]):
    identifier = serializers.CharField()
    role_code = serializers.CharField(max_length=80)
    branch_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class StaffUpdateSerializer(serializers.Serializer[dict[str, object]]):
    role_code = serializers.CharField(max_length=80, required=False)
    branch_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    status = serializers.ChoiceField(choices=OfficeMembership.Status.choices, required=False)


class OfficeDocumentWriteSerializer(serializers.Serializer[dict[str, object]]):
    document_type = serializers.CharField(max_length=64)
    storage_object_key = serializers.CharField()
    sha256 = serializers.RegexField(regex=r"^[0-9a-fA-F]{64}$")
    issued_at = serializers.DateField(required=False, allow_null=True)
    expires_at = serializers.DateField(required=False, allow_null=True)
    is_critical = serializers.BooleanField(default=True)


class OfficeDocumentReviewSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(
        choices=[OfficeDocument.Status.VERIFIED, OfficeDocument.Status.REJECTED]
    )
    reason = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PayoutAccountSerializer(serializers.ModelSerializer[OfficePayoutAccount]):
    class Meta:
        model = OfficePayoutAccount
        fields = [
            "id",
            "method_type",
            "account_holder_name",
            "account_reference_last4",
            "status",
            "verified_at",
            "effective_at",
            "created_by_id",
            "approved_by_id",
            "created_at",
        ]


class PayoutAccountWriteSerializer(serializers.Serializer[dict[str, object]]):
    method_type = serializers.ChoiceField(choices=OfficePayoutAccount.MethodType.choices)
    account_holder_name = serializers.CharField(max_length=200)
    account_reference = serializers.CharField(min_length=4, max_length=500, write_only=True)
