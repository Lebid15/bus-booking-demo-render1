from __future__ import annotations

from rest_framework import serializers


class PublicLocationSummarySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    name = serializers.CharField()
    type = serializers.CharField()
    address = serializers.CharField(allow_null=True)


class PublicPartySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    name = serializers.CharField()


class PublicPolicySummarySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    code = serializers.CharField()
    policy_type = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField()
    version_no = serializers.IntegerField()
    language = serializers.CharField()


class PublicTripSummarySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    office = PublicPartySerializer()
    operator = PublicPartySerializer()
    origin = PublicLocationSummarySerializer()
    destination = PublicLocationSummarySerializer()
    departure_at = serializers.DateTimeField()
    arrival_at = serializers.DateTimeField(allow_null=True)
    currency = serializers.CharField()
    from_price = serializers.CharField()
    available_seats = serializers.IntegerField()
    payment_methods = serializers.ListField(child=serializers.CharField())
    cancellation_summary = serializers.CharField(allow_blank=True)
    quote_version = serializers.IntegerField()
    policy_summaries = PublicPolicySummarySerializer(many=True)
