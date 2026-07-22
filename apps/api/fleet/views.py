from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from fleet.models import Driver, SeatLayout, Vehicle
from fleet.serializers import (
    DriverSerializer,
    DriverWriteSerializer,
    SeatLayoutSerializer,
    SeatLayoutWriteSerializer,
    VehicleSerializer,
    VehicleWriteSerializer,
)
from fleet.services import (
    create_driver,
    create_seat_layout,
    create_vehicle,
    update_driver,
    update_vehicle,
    version_seat_layout,
)
from organizations.permissions import HasOfficeContext


class SeatLayoutListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    @extend_schema(responses={200: SeatLayoutSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = SeatLayout.objects.filter(office=request.office_context.office).prefetch_related(
            "seats", "adjacencies__seat_a", "adjacencies__seat_b"
        )
        return Response(SeatLayoutSerializer(queryset, many=True).data)

    @extend_schema(request=SeatLayoutWriteSerializer, responses={200: SeatLayoutSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = SeatLayoutWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        layout = create_seat_layout(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        layout = SeatLayout.objects.prefetch_related(
            "seats", "adjacencies__seat_a", "adjacencies__seat_b"
        ).get(pk=layout.pk)
        return Response(SeatLayoutSerializer(layout).data)


class SeatLayoutDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    def _get_layout(self, request, layout_id: str) -> SeatLayout:  # type: ignore[no-untyped-def]
        layout = SeatLayout.objects.filter(
            id=layout_id,
            office=request.office_context.office,
        ).prefetch_related("seats", "adjacencies__seat_a", "adjacencies__seat_b").first()
        if layout is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        return layout

    @extend_schema(responses={200: SeatLayoutSerializer})
    def get(self, request, layout_id: str):  # type: ignore[no-untyped-def]
        return Response(SeatLayoutSerializer(self._get_layout(request, layout_id)).data)

    @extend_schema(request=SeatLayoutWriteSerializer, responses={200: SeatLayoutSerializer})
    def patch(self, request, layout_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = SeatLayoutWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        layout = version_seat_layout(
            context=request.office_context,
            actor=request.user,
            request=request,
            layout_id=layout_id,
            data=serializer.validated_data,
        )
        layout = SeatLayout.objects.prefetch_related(
            "seats", "adjacencies__seat_a", "adjacencies__seat_b"
        ).get(pk=layout.pk)
        return Response(SeatLayoutSerializer(layout).data)


class VehicleListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    @extend_schema(responses={200: VehicleSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = Vehicle.objects.filter(office=request.office_context.office).select_related("seat_layout")
        return Response(VehicleSerializer(queryset, many=True).data)

    @extend_schema(request=VehicleWriteSerializer, responses={200: VehicleSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = VehicleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vehicle = create_vehicle(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        return Response(VehicleSerializer(vehicle).data)


class VehicleDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    @extend_schema(request=VehicleWriteSerializer, responses={200: VehicleSerializer})
    def patch(self, request, vehicle_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = VehicleWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        vehicle = update_vehicle(
            context=request.office_context,
            actor=request.user,
            request=request,
            vehicle_id=vehicle_id,
            data=serializer.validated_data,
        )
        return Response(VehicleSerializer(vehicle).data)


class DriverListCreateView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    @extend_schema(responses={200: DriverSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        office = request.office_context.office
        queryset = (
            Driver.objects.none()
            if office.operator_id is None
            else Driver.objects.filter(operator_id=office.operator_id)
        )
        return Response(DriverSerializer(queryset, many=True).data)

    @extend_schema(request=DriverWriteSerializer, responses={200: DriverSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = DriverWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        driver = create_driver(
            context=request.office_context,
            actor=request.user,
            request=request,
            data=serializer.validated_data,
        )
        return Response(DriverSerializer(driver).data)


class DriverDetailView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.fleet.manage"

    @extend_schema(request=DriverWriteSerializer, responses={200: DriverSerializer})
    def patch(self, request, driver_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = DriverWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        driver = update_driver(
            context=request.office_context,
            actor=request.user,
            request=request,
            driver_id=driver_id,
            data=serializer.validated_data,
        )
        return Response(DriverSerializer(driver).data)
