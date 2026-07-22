from __future__ import annotations

from collections.abc import Mapping

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.change_services import (
    cancel_public_booking,
    change_booking_seat,
    get_cancellation_quote,
    replace_booking_passenger,
)
from bookings.serializers import (
    BookingLookupRequestSerializer,
    CancelBookingRequestSerializer,
    CancellationQuoteResponseSerializer,
    CreateBookingRequestSerializer,
    LinkGuestBookingSerializer,
    OfficeBookingCommandSerializer,
    PublicBookingResponseSerializer,
    SeatHoldReleaseResponseSerializer,
    SeatHoldRequestSerializer,
    SeatHoldResponseSerializer,
)
from bookings.services import (
    create_public_booking,
    create_public_seat_hold,
    get_public_booking,
    link_guest_booking_to_customer,
    list_customer_bookings,
    lookup_public_booking,
    release_public_seat_hold,
)
from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from organizations.permissions import HasOfficeContext
from securityops.services import enforce_public_booking_risk
from trips.public_services import parse_hold_token


def _require_passenger_genders(data: object) -> None:
    passengers = data.get("passengers", []) if isinstance(data, Mapping) else []
    if isinstance(passengers, list) and any(
        not isinstance(passenger, Mapping) or not passenger.get("gender") for passenger in passengers
    ):
        raise DomainAPIException("PASSENGER_GENDER_REQUIRED")


class PublicSeatHoldCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=SeatHoldRequestSerializer, responses={200: SeatHoldResponseSerializer})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        _require_passenger_genders(request.data)
        serializer = SeatHoldRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = create_public_seat_hold(
            trip_id=trip_id,
            payload=serializer.validated_data,
            idempotency_key=key,
            request=request,
        )
        return Response(SeatHoldResponseSerializer(response).data)


class PublicSeatHoldReleaseView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=None, responses={200: SeatHoldReleaseResponseSerializer})
    def post(self, request, hold_token: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        return Response({"released": release_public_seat_hold(hold_token=hold_token)})


class PublicBookingCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        request=CreateBookingRequestSerializer,
        responses={200: PublicBookingResponseSerializer},
    )
    def post(self, request):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        _require_passenger_genders(request.data)
        serializer = CreateBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parsed_hold = parse_hold_token(str(serializer.validated_data["hold_token"]))
        if parsed_hold is not None:
            enforce_public_booking_risk(
                subject_id=parsed_hold[0],
                payload=dict(serializer.validated_data),
                request=request,
            )
        response = create_public_booking(
            payload=serializer.validated_data,
            idempotency_key=key,
            request=request,
        )
        return Response(PublicBookingResponseSerializer(response).data)


class PublicBookingLookupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=BookingLookupRequestSerializer, responses={200: PublicBookingResponseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = BookingLookupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = lookup_public_booking(request=request, **serializer.validated_data)
        return Response(PublicBookingResponseSerializer(response).data)


class PublicBookingDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[OpenApiParameter("manage_token", str, required=True)],
        responses={200: PublicBookingResponseSerializer},
    )
    def get(self, request, pnr: str):  # type: ignore[no-untyped-def]
        token = str(request.query_params.get("manage_token", ""))
        if not token:
            raise DomainAPIException("AUTH_REQUIRED")
        response = get_public_booking(pnr=pnr, manage_token=token)
        return Response(PublicBookingResponseSerializer(response).data)


class PublicBookingCancellationQuoteView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[
            OpenApiParameter("manage_token", str, required=True),
            OpenApiParameter("passenger_id", str, required=False, many=True),
        ],
        responses={200: CancellationQuoteResponseSerializer},
    )
    def get(self, request, pnr: str):  # type: ignore[no-untyped-def]
        token = str(request.query_params.get("manage_token", ""))
        if not token:
            raise DomainAPIException("AUTH_REQUIRED")
        response = get_cancellation_quote(
            pnr=pnr,
            manage_token=token,
            passenger_ids=request.query_params.getlist("passenger_id") or None,
        )
        return Response(CancellationQuoteResponseSerializer(response).data)


class PublicBookingCancelView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[OpenApiParameter("manage_token", str, required=True)],
        request=CancelBookingRequestSerializer,
        responses={200: PublicBookingResponseSerializer},
    )
    def post(self, request, pnr: str):  # type: ignore[no-untyped-def]
        token = str(request.query_params.get("manage_token", ""))
        if not token:
            raise DomainAPIException("AUTH_REQUIRED")
        serializer = CancelBookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = cancel_public_booking(
            pnr=pnr,
            manage_token=token,
            idempotency_key=require_idempotency_key(request),
            request=request,
            **serializer.validated_data,
        )
        return Response(PublicBookingResponseSerializer(response).data)


class MyBookingsListView(APIView):
    @extend_schema(responses={200: PublicBookingResponseSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        status_filter = request.query_params.get("status")
        response = list_customer_bookings(user=request.user, status_filter=status_filter)
        return Response(PublicBookingResponseSerializer(response, many=True).data)  # type: ignore[arg-type]


class MyBookingLinkView(APIView):
    @extend_schema(request=LinkGuestBookingSerializer, responses={200: PublicBookingResponseSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        serializer = LinkGuestBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = link_guest_booking_to_customer(user=request.user, **serializer.validated_data)
        return Response(PublicBookingResponseSerializer(response).data)


class OfficeBookingCommandView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.booking.manage"

    @extend_schema(request=OfficeBookingCommandSerializer, responses={200: PublicBookingResponseSerializer})
    def post(self, request, booking_id: str):  # type: ignore[no-untyped-def]
        idempotency_key = require_idempotency_key(request)
        serializer = OfficeBookingCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        command = str(data.pop("command"))
        passenger_id = data.pop("passenger_id")
        if command == "replace_passenger":
            response = replace_booking_passenger(
                context=request.office_context,
                actor=request.user,
                request=request,
                booking_id=booking_id,
                passenger_id=passenger_id,
                data=data,
                idempotency_key=idempotency_key,
            )
        else:
            response = change_booking_seat(
                context=request.office_context,
                actor=request.user,
                request=request,
                booking_id=booking_id,
                passenger_id=passenger_id,
                target_seat_id=data["target_seat_id"],
                reason_code=str(data.get("reason_code") or "seat_change"),
                idempotency_key=idempotency_key,
            )
        return Response(PublicBookingResponseSerializer(response).data)
