from __future__ import annotations

from rest_framework import serializers

from fleet.models import Driver, SeatAdjacency, SeatLayout, SeatLayoutSeat, Vehicle


class SeatSerializer(serializers.ModelSerializer[SeatLayoutSeat]):
    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(source="seat_code")
    row = serializers.IntegerField(source="row_no")
    column = serializers.IntegerField(source="column_no")
    type = serializers.CharField(source="seat_type")
    sellable = serializers.BooleanField(source="is_sellable")

    class Meta:
        model = SeatLayoutSeat
        fields = ["id", "code", "row", "column", "type", "sellable", "metadata"]


class SeatAdjacencySerializer(serializers.ModelSerializer[SeatAdjacency]):
    seat_a = serializers.CharField(source="seat_a.seat_code")
    seat_b = serializers.CharField(source="seat_b.seat_code")
    type = serializers.CharField(source="adjacency_type")

    class Meta:
        model = SeatAdjacency
        fields = ["seat_a", "seat_b", "type"]


class SeatLayoutSerializer(serializers.ModelSerializer[SeatLayout]):
    id = serializers.UUIDField(read_only=True)
    seats = SeatSerializer(many=True)
    adjacencies = SeatAdjacencySerializer(many=True)

    class Meta:
        model = SeatLayout
        fields = ["id", "name", "layout_type", "seat_count", "version", "status", "seats", "adjacencies"]


class SeatWriteSerializer(serializers.Serializer[dict[str, object]]):
    code = serializers.CharField(max_length=12)
    row = serializers.IntegerField(min_value=1)
    column = serializers.IntegerField(min_value=1)
    type = serializers.ChoiceField(choices=SeatLayoutSeat.SeatType.choices, default=SeatLayoutSeat.SeatType.STANDARD)
    sellable = serializers.BooleanField(default=True)
    metadata = serializers.JSONField(required=False, default=dict)


class SeatAdjacencyWriteSerializer(serializers.Serializer[dict[str, object]]):
    seat_a = serializers.CharField(max_length=12)
    seat_b = serializers.CharField(max_length=12)
    type = serializers.ChoiceField(
        choices=SeatAdjacency.AdjacencyType.choices,
        default=SeatAdjacency.AdjacencyType.SAME_UNIT,
    )


class SeatLayoutWriteSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(max_length=160)
    layout_type = serializers.ChoiceField(choices=SeatLayout.LayoutType.choices)
    status = serializers.ChoiceField(
        choices=SeatLayout.Status.choices,
        required=False,
        default=SeatLayout.Status.ACTIVE,
    )
    seats = SeatWriteSerializer(many=True)
    adjacencies = SeatAdjacencyWriteSerializer(many=True, required=False, default=list)


class VehicleSerializer(serializers.ModelSerializer[Vehicle]):
    id = serializers.CharField(source="public_id")
    seat_layout_id = serializers.SerializerMethodField()

    class Meta:
        model = Vehicle
        fields = ["id", "plate_number", "fleet_number", "seat_layout_id", "status", "make_model", "year"]

    def get_seat_layout_id(self, obj: Vehicle) -> str:
        return str(obj.seat_layout_id)


class VehicleWriteSerializer(serializers.Serializer[dict[str, object]]):
    plate_number = serializers.CharField(max_length=40, required=False)
    fleet_number = serializers.CharField(max_length=40, required=False, allow_null=True, allow_blank=True)
    seat_layout_id = serializers.CharField(required=False)
    status = serializers.ChoiceField(choices=Vehicle.Status.choices, required=False)
    make_model = serializers.CharField(max_length=160, required=False, allow_null=True, allow_blank=True)
    year = serializers.IntegerField(min_value=1980, max_value=2100, required=False, allow_null=True)


class DriverSerializer(serializers.ModelSerializer[Driver]):
    id = serializers.CharField(source="public_id")

    class Meta:
        model = Driver
        fields = ["id", "full_name", "phone", "license_last4", "license_expires_at", "status"]


class DriverWriteSerializer(serializers.Serializer[dict[str, object]]):
    full_name = serializers.CharField(max_length=160, required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    license_number = serializers.CharField(max_length=100, required=False, write_only=True)
    license_expires_at = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Driver.Status.choices, required=False)
