from __future__ import annotations

from rest_framework import serializers

from securityops.models import LegalHold, RiskAssessment


class UploadIntentRequestSerializer(serializers.Serializer[dict[str, object]]):
    purpose = serializers.CharField(max_length=60)
    filename = serializers.CharField(max_length=255)
    mime_type = serializers.CharField(max_length=120)
    size_bytes = serializers.IntegerField(min_value=1)


class UploadIntentResponseSerializer(serializers.Serializer[dict[str, object]]):
    file_id = serializers.UUIDField()
    upload_url = serializers.URLField()
    expires_at = serializers.DateTimeField()


class UploadCompleteRequestSerializer(serializers.Serializer[dict[str, object]]):
    sha256 = serializers.RegexField(r"^[0-9a-fA-F]{64}$")


class UploadCompleteResponseSerializer(serializers.Serializer[dict[str, object]]):
    file_id = serializers.UUIDField()
    scan_status = serializers.CharField()


class AccountDeletionRequestSerializer(serializers.Serializer[dict[str, object]]):
    confirmation = serializers.CharField(max_length=20)


class DataSubjectResponseSerializer(serializers.Serializer[dict[str, object]]):
    request_id = serializers.UUIDField()
    status = serializers.CharField(required=False)


class RiskChallengeVerifySerializer(serializers.Serializer[dict[str, object]]):
    code = serializers.CharField(min_length=6, max_length=12, write_only=True)


class RiskChallengeResponseSerializer(serializers.Serializer[dict[str, object]]):
    step_up_token = serializers.CharField()
    expires_at = serializers.DateTimeField()


class LegalHoldCreateSerializer(serializers.Serializer[dict[str, object]]):
    subject_type = serializers.ChoiceField(choices=LegalHold.SubjectType.choices)
    subject_id = serializers.UUIDField()
    reason = serializers.CharField(min_length=5, max_length=1000)


class LegalHoldReleaseSerializer(serializers.Serializer[dict[str, object]]):
    reason = serializers.CharField(min_length=5, max_length=1000)


class LegalHoldSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    subject_type = serializers.CharField()
    subject_id = serializers.UUIDField()
    reason = serializers.CharField()
    active = serializers.BooleanField()
    placed_at = serializers.DateTimeField()
    released_at = serializers.DateTimeField(allow_null=True)


class RiskAssessmentSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    subject_type = serializers.ChoiceField(choices=RiskAssessment.SubjectType.choices)
    subject_id = serializers.UUIDField()
    score = serializers.DecimalField(max_digits=6, decimal_places=3)
    decision = serializers.ChoiceField(choices=RiskAssessment.Decision.choices)
    model_version = serializers.CharField()
    signals = serializers.JSONField()
    review_status = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
