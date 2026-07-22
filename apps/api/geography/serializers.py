from __future__ import annotations

from rest_framework import serializers

from geography.models import Location, Route, RouteStop


class LocationSerializer(serializers.ModelSerializer[Location]):
    type = serializers.CharField(source="location_type")
    parent_id = serializers.CharField(source="parent.public_id", allow_null=True, read_only=True)
    address = serializers.CharField(source="address_text", allow_null=True, read_only=True)

    class Meta:
        model = Location
        fields = [
            "public_id",
            "type",
            "parent_id",
            "name_ar",
            "name_en",
            "address",
            "latitude",
            "longitude",
            "status",
        ]


class PublicLocationSerializer(serializers.ModelSerializer[Location]):
    id = serializers.CharField(source="public_id")
    name = serializers.CharField(source="name_ar")
    type = serializers.CharField(source="location_type")
    address = serializers.CharField(source="address_text", allow_null=True)

    class Meta:
        model = Location
        fields = ["id", "name", "type", "address"]


class LocationWriteSerializer(serializers.Serializer[dict[str, object]]):
    type = serializers.ChoiceField(choices=Location.LocationType.choices, required=False)
    parent_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    name_ar = serializers.CharField(max_length=160, required=False)
    name_en = serializers.CharField(max_length=160, required=False, allow_null=True, allow_blank=True)
    address = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Location.Status.choices, required=False)


class RouteStopSerializer(serializers.ModelSerializer[RouteStop]):
    location_id = serializers.CharField(source="location.public_id")

    class Meta:
        model = RouteStop
        fields = ["sequence_no", "location_id", "stop_type", "offset_minutes"]


class RouteSerializer(serializers.ModelSerializer[Route]):
    origin_id = serializers.CharField(source="origin_location.public_id")
    destination_id = serializers.CharField(source="destination_location.public_id")
    stops = RouteStopSerializer(many=True)

    class Meta:
        model = Route
        fields = ["public_id", "origin_id", "destination_id", "name_ar", "status", "stops"]


class RouteStopWriteSerializer(serializers.Serializer[dict[str, object]]):
    sequence_no = serializers.IntegerField(min_value=1)
    location_id = serializers.CharField()
    stop_type = serializers.ChoiceField(choices=RouteStop.StopType.choices)
    offset_minutes = serializers.IntegerField(min_value=0, default=0)


class RouteWriteSerializer(serializers.Serializer[dict[str, object]]):
    origin_id = serializers.CharField(required=False)
    destination_id = serializers.CharField(required=False)
    name_ar = serializers.CharField(max_length=200, required=False)
    status = serializers.ChoiceField(choices=Route.Status.choices, required=False)
    stops = RouteStopWriteSerializer(many=True, required=False)
