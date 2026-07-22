from __future__ import annotations

from typing import Any, cast

from rest_framework import serializers

from bookings.models import BookingPassenger


class PassengerInputSerializer(serializers.Serializer[dict[str, object]]):
    full_name = serializers.CharField(min_length=2, max_length=160)
    gender = serializers.ChoiceField(choices=BookingPassenger.Gender.choices)
    passenger_type = serializers.ChoiceField(choices=BookingPassenger.PassengerType.choices)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    nationality_code = serializers.CharField(
        required=False, allow_null=True, allow_blank=True, min_length=2, max_length=2
    )
    seat_id = serializers.UUIDField(required=False)


class SeatHoldRequestSerializer(serializers.Serializer[dict[str, object]]):
    seat_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=8)
    passengers = PassengerInputSerializer(many=True)
    quote_version = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        seat_ids = cast(list[Any], attrs["seat_ids"])
        passengers = cast(list[dict[str, Any]], attrs["passengers"])
        if not 1 <= len(passengers) <= 8:
            raise serializers.ValidationError({"passengers": "count_range_1_8"})
        if len(seat_ids) != len(set(seat_ids)):
            raise serializers.ValidationError({"seat_ids": "duplicate_seat_ids"})
        if len(seat_ids) != len(passengers):
            raise serializers.ValidationError({"passengers": "count_must_match_seats"})
        passenger_seat_ids = [passenger.get("seat_id") for passenger in passengers if passenger.get("seat_id")]
        if passenger_seat_ids and set(passenger_seat_ids) != set(seat_ids):
            raise serializers.ValidationError({"passengers": "seat_mapping_mismatch"})
        return attrs


class MoneySerializer(serializers.Serializer[dict[str, object]]):
    amount = serializers.CharField()
    currency = serializers.CharField()


class BookingQuoteSerializer(serializers.Serializer[dict[str, object]]):
    subtotal = MoneySerializer()
    discount = MoneySerializer()
    fees = MoneySerializer()
    total = MoneySerializer()
    payment_deadline_at = serializers.DateTimeField(allow_null=True)
    policy_version_ids = serializers.ListField(child=serializers.CharField())
    quote_version = serializers.IntegerField()


class SeatHoldResponseSerializer(serializers.Serializer[dict[str, object]]):
    hold_token = serializers.CharField()
    expires_at = serializers.DateTimeField()
    quote = BookingQuoteSerializer()


class SeatHoldReleaseResponseSerializer(serializers.Serializer[dict[str, object]]):
    released = serializers.BooleanField()


class BookingContactSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField(min_length=2, max_length=160)
    phone = serializers.CharField(min_length=8, max_length=20)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)


class CreateBookingRequestSerializer(serializers.Serializer[dict[str, object]]):
    trip_id = serializers.CharField(max_length=26)
    hold_token = serializers.CharField(min_length=36, max_length=200)
    contact = BookingContactSerializer()
    passengers = PassengerInputSerializer(many=True)
    payment_method = serializers.ChoiceField(
        choices=[
            ("office_cash", "Office cash"),
            ("manual_transfer", "Manual transfer"),
            ("electronic", "Electronic"),
        ]
    )
    accepted_policy_version_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )
    client_reference = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=120,
    )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        passengers = cast(list[dict[str, Any]], attrs["passengers"])
        if not 1 <= len(passengers) <= 8:
            raise serializers.ValidationError({"passengers": "count_range_1_8"})
        seat_ids = [passenger.get("seat_id") for passenger in passengers]
        if any(seat_id is None for seat_id in seat_ids):
            raise serializers.ValidationError({"passengers": "seat_id_required"})
        if len(seat_ids) != len(set(seat_ids)):
            raise serializers.ValidationError({"passengers": "duplicate_seat_id"})
        return attrs


class BookingTripLocationSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    name = serializers.CharField()


class BookingTripOfficeSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    name = serializers.CharField()


class BookingTripSummarySerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    departure_at = serializers.DateTimeField()
    arrival_at = serializers.DateTimeField(allow_null=True)
    origin = BookingTripLocationSerializer()
    destination = BookingTripLocationSerializer()
    office = BookingTripOfficeSerializer()


class BookingContactOutputSerializer(serializers.Serializer[dict[str, object]]):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField(allow_null=True)


class TicketOutputSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    status = serializers.CharField()
    qr_data = serializers.CharField()
    seat_code = serializers.CharField()
    pdf_url = serializers.CharField(allow_null=True)


class BookingPassengerOutputSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    gender = serializers.CharField()
    passenger_type = serializers.CharField()
    date_of_birth = serializers.DateField(allow_null=True)
    nationality_code = serializers.CharField(allow_null=True)
    boarding_status = serializers.CharField()
    status = serializers.CharField()
    seat_id = serializers.UUIDField(allow_null=True)
    seat_code = serializers.CharField(allow_null=True)
    ticket = TicketOutputSerializer(allow_null=True)


class BookingLookupRequestSerializer(serializers.Serializer[dict[str, object]]):
    pnr = serializers.CharField(min_length=6, max_length=12)
    contact_verifier = serializers.CharField(min_length=4, max_length=254)


class BookingTripChangeSerializer(serializers.Serializer[dict[str, object]]):
    change_id = serializers.UUIDField()
    change_type = serializers.CharField()
    classification = serializers.CharField()
    status = serializers.CharField()
    response_deadline_at = serializers.DateTimeField(allow_null=True)
    previous_snapshot = serializers.JSONField()
    new_snapshot = serializers.JSONField()


class PublicBookingResponseSerializer(serializers.Serializer[dict[str, object]]):
    id = serializers.CharField()
    pnr = serializers.CharField()
    status = serializers.CharField()
    payment_status = serializers.CharField()
    trip = BookingTripSummarySerializer()
    contact = BookingContactOutputSerializer()
    passengers = BookingPassengerOutputSerializer(many=True)
    pricing = BookingQuoteSerializer()
    payment_deadline_at = serializers.DateTimeField(allow_null=True)
    payment_methods = serializers.ListField(child=serializers.CharField())
    outstanding_amount = serializers.CharField()
    created_at = serializers.DateTimeField()
    manage_actions = serializers.ListField(child=serializers.CharField())
    trip_changes = BookingTripChangeSerializer(many=True)
    manage_token = serializers.CharField(required=False)


class LinkGuestBookingSerializer(serializers.Serializer[dict[str, object]]):
    pnr = serializers.CharField(min_length=6, max_length=12)
    manage_token = serializers.CharField(min_length=20, max_length=200)


class CancellationPassengerQuoteSerializer(serializers.Serializer[dict[str, object]]):
    passenger_id = serializers.UUIDField()
    full_name = serializers.CharField()
    seat_id = serializers.UUIDField()
    seat_code = serializers.CharField()
    subtotal_amount = serializers.CharField()
    discount_amount = serializers.CharField()
    fee_amount = serializers.CharField()
    total_amount = serializers.CharField()
    refund_amount = serializers.CharField()
    retained_amount = serializers.CharField()


class CancellationQuoteResponseSerializer(serializers.Serializer[dict[str, object]]):
    allowed = serializers.BooleanField()
    refund_amount = MoneySerializer()
    retained_amount = MoneySerializer()
    reason = serializers.CharField()
    expires_at = serializers.DateTimeField()
    quote_token = serializers.CharField()
    passengers = CancellationPassengerQuoteSerializer(many=True)


class CancelBookingRequestSerializer(serializers.Serializer[dict[str, object]]):
    quote_token = serializers.CharField(min_length=20)
    reason_code = serializers.CharField(required=False, allow_blank=True, max_length=80)


class OfficeBookingCommandSerializer(serializers.Serializer[dict[str, object]]):
    command = serializers.ChoiceField(choices=["replace_passenger", "change_seat"])
    passenger_id = serializers.UUIDField()
    target_seat_id = serializers.UUIDField(required=False)
    full_name = serializers.CharField(required=False, min_length=2, max_length=160)
    gender = serializers.ChoiceField(choices=BookingPassenger.Gender.choices, required=False)
    passenger_type = serializers.ChoiceField(choices=BookingPassenger.PassengerType.choices, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    nationality_code = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2)
    reason_code = serializers.CharField(required=False, allow_blank=True, max_length=80)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        command = attrs["command"]
        if command == "change_seat" and "target_seat_id" not in attrs:
            raise serializers.ValidationError({"target_seat_id": "required"})
        if command == "replace_passenger" and not any(
            key in attrs for key in ("full_name", "gender", "passenger_type", "date_of_birth", "nationality_code")
        ):
            raise serializers.ValidationError({"command": "replacement_fields_required"})
        return attrs
