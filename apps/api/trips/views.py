from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

from django.db.models import QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from identity.models import UserSession
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from trips.models import SeatHold, Trip
from trips.public_serializers import PublicTripSummarySerializer
from trips.public_services import get_public_trip, public_seat_map, search_public_trips
from trips.reallocation_services import (
    apply_vehicle_reallocation,
    close_interrupted_trip,
    preview_vehicle_reallocation,
    resolve_interruption_booking,
    respond_to_trip_change,
    serialize_plan,
)
from trips.serializers import (
    InterruptionBookingResolutionSerializer,
    InterruptionCloseSerializer,
    SeatMapSerializer,
    TripChangeResponseRequestSerializer,
    TripCommandSerializer,
    TripPatchSerializer,
    TripSerializer,
    TripWriteSerializer,
    VehicleReallocationApplySerializer,
    VehicleReallocationPreviewSerializer,
)
from trips.services import command_trip, create_trip, seat_map_for_trip, update_trip


class OfficeTripListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    @extend_schema(
        responses={200: TripSerializer(many=True)},
        parameters=[
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("date_from", str, required=False),
            OpenApiParameter("date_to", str, required=False),
        ],
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = (
            Trip.objects.filter(office=request.office_context.office)
            .select_related(
                "office",
                "operator",
                "branch",
                "route__origin_location",
                "route__destination_location",
                "vehicle",
                "driver",
                "seat_layout",
            )
            .prefetch_related("stops__location", "seats__layout_seat")
        )
        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(scheduled_departure_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_departure_at__date__lte=date_to)
        return Response(TripSerializer(queryset, many=True).data)

    @extend_schema(request=TripWriteSerializer, responses={200: TripSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = TripWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = create_trip(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        return Response(TripSerializer(_trip_queryset(request).get(id=trip.id)).data)


def _trip_queryset(request: Any) -> QuerySet[Trip]:
    return (
        Trip.objects.filter(office=request.office_context.office)
        .select_related(
            "office",
            "operator",
            "branch",
            "route__origin_location",
            "route__destination_location",
            "vehicle",
            "driver",
            "seat_layout",
        )
        .prefetch_related("stops__location", "seats__layout_seat")
    )


class OfficeTripDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    def _get(self, request, trip_id: str) -> Trip:  # type: ignore[no-untyped-def]
        trip = _trip_queryset(request).filter(public_id=trip_id).first()
        if trip is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        return trip

    @extend_schema(responses={200: TripSerializer})
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        return Response(TripSerializer(self._get(request, trip_id)).data)

    @extend_schema(request=TripPatchSerializer, responses={200: TripSerializer})
    def patch(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = TripPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = update_trip(
            context=request.office_context,
            actor=request.user,
            request=request,
            trip_id=trip_id,
            data=serializer.validated_data,
        )
        return Response(TripSerializer(_trip_queryset(request).get(id=trip.id)).data)


class OfficeTripCommandView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    @extend_schema(request=TripCommandSerializer, responses={200: TripSerializer})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = TripCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = command_trip(
            context=request.office_context,
            actor=request.user,
            request=request,
            trip_id=trip_id,
            data=serializer.validated_data,
        )
        return Response(TripSerializer(_trip_queryset(request).get(id=trip.id)).data)


class OfficeTripSeatMapView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    @extend_schema(responses={200: SeatMapSerializer})
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        trip = _trip_queryset(request).filter(public_id=trip_id).first()
        if trip is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        session = request.auth if isinstance(request.auth, UserSession) else None
        active_expiry = (
            SeatHold.objects.filter(
                trip=trip,
                status=SeatHold.Status.ACTIVE,
                expires_at__gt=timezone.now(),
            )
            .order_by("expires_at")
            .values_list("expires_at", flat=True)
            .first()
        )
        payload = {
            "trip_id": trip.public_id,
            "layout_version": trip.seat_layout.version,
            "expires_at": active_expiry or timezone.now() + timedelta(seconds=30),
            "seats": seat_map_for_trip(trip, session_id=session.id if session else None),
        }
        return Response(SeatMapSerializer(payload).data)


class PublicTripSearchView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        responses={200: PublicTripSummarySerializer(many=True)},
        parameters=[
            OpenApiParameter("origin_id", str, required=True),
            OpenApiParameter("destination_id", str, required=True),
            OpenApiParameter("date", str, required=True),
            OpenApiParameter("passengers", int, required=False),
        ],
    )
    def get(self, request):  # type: ignore[no-untyped-def]
        results = search_public_trips(
            origin_id=request.query_params.get("origin_id", ""),
            destination_id=request.query_params.get("destination_id", ""),
            service_date_raw=request.query_params.get("date", ""),
            passengers_raw=request.query_params.get("passengers", 1),
        )
        return Response(PublicTripSummarySerializer(instance=cast(Any, results), many=True).data)


class PublicTripDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(responses={200: PublicTripSummarySerializer})
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        _, payload = get_public_trip(trip_id)
        return Response(PublicTripSummarySerializer(payload).data)


class PublicTripSeatMapView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        responses={200: SeatMapSerializer},
        parameters=[OpenApiParameter("session_token", str, required=False)],
    )
    def get(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        trip, _ = get_public_trip(trip_id)
        payload = public_seat_map(trip, hold_token=request.query_params.get("session_token"))
        return Response(SeatMapSerializer(payload).data)


class OfficeTripVehicleReallocationPreviewView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    @extend_schema(request=VehicleReallocationPreviewSerializer, responses={200: dict})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = VehicleReallocationPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = preview_vehicle_reallocation(
            context=request.office_context,
            actor=request.user,
            request=request,
            trip_id=trip_id,
            target_vehicle_id=str(serializer.validated_data["target_vehicle_id"]),
            version=int(serializer.validated_data["version"]),
            idempotency_key=key,
        )
        return Response(serialize_plan(plan))


class OfficeTripVehicleReallocationApplyView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.trip.manage"

    @extend_schema(request=VehicleReallocationApplySerializer, responses={200: dict})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = VehicleReallocationApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = apply_vehicle_reallocation(
            context=request.office_context,
            actor=request.user,
            request=request,
            trip_id=trip_id,
            plan_id=str(serializer.validated_data["plan_id"]),
            idempotency_key=key,
        )
        return Response(serialize_plan(plan))


class PublicTripChangeResponseView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=TripChangeResponseRequestSerializer, responses={200: dict})
    def post(self, request, pnr: str, change_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = TripChangeResponseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = respond_to_trip_change(
            pnr=pnr,
            manage_token=request.query_params.get("manage_token", ""),
            change_id=change_id,
            choice=str(serializer.validated_data["choice"]),
            idempotency_key=key,
        )
        return Response(
            {
                "change_id": str(response.change_id),
                "booking_id": response.booking.public_id,
                "status": response.status,
                "responded_at": response.responded_at,
            }
        )


class PlatformTripInterruptionBookingView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.trip.incident.manage"

    @extend_schema(request=InterruptionBookingResolutionSerializer, responses={200: dict})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = InterruptionBookingResolutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = resolve_interruption_booking(
            actor=request.user,
            request=request,
            trip_id=trip_id,
            booking_id=str(serializer.validated_data["booking_id"]),
            resolution=str(serializer.validated_data["resolution"]),
            details=dict(serializer.validated_data.get("details", {})),
            idempotency_key=key,
        )
        return Response(
            {
                "id": str(result.id),
                "booking_id": result.booking.public_id,
                "status": result.status,
                "resolved_at": result.resolved_at,
            }
        )


class PlatformTripInterruptionCloseView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.trip.incident.manage"

    @extend_schema(request=InterruptionCloseSerializer, responses={200: TripSerializer})
    def post(self, request, trip_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = InterruptionCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip = close_interrupted_trip(
            actor=request.user,
            request=request,
            trip_id=trip_id,
            outcome=str(serializer.validated_data["outcome"]),
            version=int(serializer.validated_data["version"]),
            idempotency_key=key,
        )
        return Response(TripSerializer(_platform_trip_queryset().get(id=trip.id)).data)


def _platform_trip_queryset() -> QuerySet[Trip]:
    return Trip.objects.select_related(
        "office",
        "operator",
        "branch",
        "route__origin_location",
        "route__destination_location",
        "vehicle",
        "driver",
        "seat_layout",
    ).prefetch_related("stops__location", "seats__layout_seat")
