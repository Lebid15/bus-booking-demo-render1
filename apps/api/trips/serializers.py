from __future__ import annotations

from django.db.models import Count
from rest_framework import serializers

from bookings.models import BookingPassenger
from geography.serializers import LocationSerializer
from trips.models import Trip, TripChange, TripStop
from trips.services import seat_map_for_trip


class TripStopSerializer(serializers.ModelSerializer[TripStop]):
    location = LocationSerializer(read_only=True)

    class Meta:
        model = TripStop
        fields = ["sequence_no", "location", "scheduled_at", "actual_at", "stop_type"]


class TripSerializer(serializers.ModelSerializer[Trip]):
    id = serializers.CharField(source="public_id")
    office = serializers.SerializerMethodField()
    operator = serializers.SerializerMethodField()
    origin = LocationSerializer(source="route.origin_location", read_only=True)
    destination = LocationSerializer(source="route.destination_location", read_only=True)
    departure_at = serializers.DateTimeField(source="scheduled_departure_at")
    arrival_at = serializers.DateTimeField(source="scheduled_arrival_at", allow_null=True)
    from_price = serializers.DecimalField(source="base_price", max_digits=18, decimal_places=2)
    available_seats = serializers.SerializerMethodField()
    payment_methods = serializers.SerializerMethodField()
    cancellation_summary = serializers.SerializerMethodField()
    boarding_counts = serializers.SerializerMethodField()
    stops = TripStopSerializer(many=True, read_only=True)
    branch_id = serializers.CharField(source="branch.public_id", read_only=True)
    route_id = serializers.CharField(source="route.public_id", read_only=True)
    vehicle_id = serializers.CharField(source="vehicle.public_id", read_only=True)
    driver_id = serializers.CharField(source="driver.public_id", read_only=True, allow_null=True)
    seat_layout_id = serializers.UUIDField(read_only=True)
    policy_snapshot = serializers.JSONField(read_only=True)
    pricing_snapshot = serializers.JSONField(read_only=True)

    class Meta:
        model = Trip
        fields = [
            "id",
            "office",
            "operator",
            "origin",
            "destination",
            "departure_at",
            "arrival_at",
            "currency",
            "from_price",
            "available_seats",
            "payment_methods",
            "cancellation_summary",
            "status",
            "version",
            "boarding_counts",
            "branch_id",
            "route_id",
            "vehicle_id",
            "driver_id",
            "seat_layout_id",
            "booking_open_at",
            "booking_close_at",
            "boarding_open_at",
            "boarding_close_at",
            "policy_snapshot",
            "pricing_snapshot",
            "stops",
            "actual_departure_at",
            "actual_arrival_at",
        ]

    def get_office(self, obj: Trip) -> dict[str, str]:
        return {"id": obj.office.public_id, "name": obj.office.trade_name}

    def get_operator(self, obj: Trip) -> dict[str, str]:
        return {"id": obj.operator.public_id, "name": obj.operator.trade_name or obj.operator.legal_name}

    def get_available_seats(self, obj: Trip) -> int:
        return sum(1 for item in seat_map_for_trip(obj) if item["status"] == "available")

    def get_payment_methods(self, obj: Trip) -> list[str]:
        methods = obj.pricing_snapshot.get("payment_methods", [])
        return [str(value) for value in methods] if isinstance(methods, list) else []

    def get_cancellation_summary(self, obj: Trip) -> str:
        policy = obj.policy_snapshot.get("cancellation", {})
        if not isinstance(policy, dict):
            return ""
        rules = policy.get("rules", {})
        if isinstance(rules, dict) and rules.get("summary"):
            return str(rules["summary"])
        return str(policy.get("title", ""))

    def get_boarding_counts(self, obj: Trip) -> dict[str, int]:
        counts = {choice[0]: 0 for choice in BookingPassenger.BoardingStatus.choices}
        rows = (
            BookingPassenger.objects.filter(booking__trip=obj)
            .values("boarding_status")
            .order_by()
            .annotate(total=Count("id"))
        )
        for row in rows:
            counts[str(row["boarding_status"])] = int(row["total"])
        return counts


class TripWriteSerializer(serializers.Serializer[dict[str, object]]):
    route_id = serializers.CharField()
    branch_id = serializers.CharField()
    operator_id = serializers.CharField()
    vehicle_id = serializers.CharField()
    driver_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    scheduled_departure_at = serializers.DateTimeField()
    scheduled_arrival_at = serializers.DateTimeField(required=False, allow_null=True)
    currency = serializers.CharField(min_length=3, max_length=3)
    base_price = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)
    policy_version_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    payment_methods = serializers.ListField(
        child=serializers.CharField(max_length=40),
        required=False,
        default=list,
    )
    booking_open_at = serializers.DateTimeField(required=False, allow_null=True)
    booking_close_at = serializers.DateTimeField(required=False, allow_null=True)
    boarding_open_at = serializers.DateTimeField(required=False, allow_null=True)
    boarding_close_at = serializers.DateTimeField(required=False, allow_null=True)


class TripPatchSerializer(serializers.Serializer[dict[str, object]]):
    scheduled_departure_at = serializers.DateTimeField(required=False)
    scheduled_arrival_at = serializers.DateTimeField(required=False, allow_null=True)
    base_price = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0, required=False)
    vehicle_id = serializers.CharField(required=False)
    driver_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    version = serializers.IntegerField(min_value=1)


class TripCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(
        choices=[
            "schedule",
            "publish",
            "open_booking",
            "open_boarding",
            "close_boarding",
            "depart",
            "arrive",
            "complete",
            "cancel",
            "interrupt",
        ]
    )
    reason_code = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=80)
    version = serializers.IntegerField(min_value=1)


class SeatAvailabilitySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    code = serializers.CharField()
    row = serializers.IntegerField()
    column = serializers.IntegerField()
    type = serializers.CharField()
    status = serializers.ChoiceField(
        choices=["available", "held_by_you", "unavailable", "policy_unavailable", "blocked"]
    )
    price = serializers.CharField(allow_null=True)


class SeatMapSerializer(serializers.Serializer[dict[str, object]]):
    trip_id = serializers.CharField()
    layout_version = serializers.IntegerField()
    expires_at = serializers.DateTimeField(allow_null=True)
    seats = SeatAvailabilitySerializer(many=True)


class TripChangeSerializer(serializers.ModelSerializer[TripChange]):
    pending_responses = serializers.SerializerMethodField()

    class Meta:
        model = TripChange
        fields = [
            "id",
            "change_type",
            "classification",
            "previous_snapshot",
            "new_snapshot",
            "response_deadline_at",
            "pending_responses",
            "created_at",
        ]

    def get_pending_responses(self, obj: TripChange) -> int:
        return obj.responses.filter(status="pending").count()


class VehicleReallocationPreviewSerializer(serializers.Serializer[dict[str, object]]):
    target_vehicle_id = serializers.CharField(max_length=26)
    version = serializers.IntegerField(min_value=1)


class VehicleReallocationApplySerializer(serializers.Serializer[dict[str, object]]):
    plan_id = serializers.UUIDField()


class TripChangeResponseRequestSerializer(serializers.Serializer[dict[str, object]]):
    choice = serializers.ChoiceField(choices=["accept", "alternative", "refund"])


class InterruptionBookingResolutionSerializer(serializers.Serializer[dict[str, object]]):
    booking_id = serializers.CharField(max_length=26)
    resolution = serializers.ChoiceField(
        choices=["service_completed", "alternative_accepted", "refund_started", "compensated"]
    )
    details = serializers.JSONField(required=False, default=dict)


class InterruptionCloseSerializer(serializers.Serializer[dict[str, object]]):
    outcome = serializers.ChoiceField(choices=["completed", "cancelled"])
    version = serializers.IntegerField(min_value=1)
