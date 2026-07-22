from rest_framework import serializers


class ContinuityCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["maintenance", "recovery", "reconcile", "reopen"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class RecoveryExerciseSerializer(serializers.Serializer[dict[str, object]]):
    backup_id = serializers.CharField()
    target_time = serializers.DateTimeField()
    restored_to_time = serializers.DateTimeField()
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()
    evidence = serializers.JSONField(required=False)


class ReleaseSerializer(serializers.Serializer[dict[str, object]]):
    version = serializers.CharField(max_length=100)
    health_passed = serializers.BooleanField()
    smoke_passed = serializers.BooleanField()
    rollback_reference = serializers.CharField(required=False, allow_blank=True, max_length=200)
    evidence = serializers.JSONField(required=False)


class IncidentSerializer(serializers.Serializer[dict[str, object]]):
    title = serializers.CharField(max_length=240)
    severity = serializers.ChoiceField(choices=["SEV1", "SEV2", "SEV3"])
    communication_channel = serializers.CharField(max_length=240)
    customer_impact = serializers.CharField(required=False, allow_blank=True)


class IncidentCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["timeline", "mitigate", "resolve", "close"])
    message = serializers.CharField(required=False, allow_blank=True)
    postmortem = serializers.CharField(required=False, allow_blank=True)


class LoadTestSerializer(serializers.Serializer[dict[str, object]]):
    scenario = serializers.CharField(max_length=160)
    started_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField()
    requests = serializers.IntegerField(min_value=1)
    error_rate_percent = serializers.DecimalField(max_digits=6, decimal_places=3, min_value=0)
    p95_ms = serializers.IntegerField(min_value=0)
    duplicate_seats = serializers.IntegerField(min_value=0)
    duplicate_financial_entries = serializers.IntegerField(min_value=0)
    slo = serializers.JSONField(required=False)
