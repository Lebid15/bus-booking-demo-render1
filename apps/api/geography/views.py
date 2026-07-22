from __future__ import annotations

from django.db import models
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.requests import require_idempotency_key
from geography.models import Location, Route
from geography.serializers import (
    LocationSerializer,
    LocationWriteSerializer,
    PublicLocationSerializer,
    RouteSerializer,
    RouteWriteSerializer,
)
from geography.services import create_location, create_route, update_location, update_route
from organizations.permissions import HasPlatformAccess


class PublicLocationListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={200: PublicLocationSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = Location.objects.filter(status=Location.Status.ACTIVE).select_related("parent")
        location_type = request.query_params.get("type")
        if location_type:
            queryset = queryset.filter(location_type=location_type)
        query = request.query_params.get("query", "").strip()
        if query:
            queryset = queryset.filter(models.Q(name_ar__icontains=query) | models.Q(name_en__icontains=query))
        return Response(PublicLocationSerializer(queryset, many=True).data)


class PlatformLocationListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.catalog.manage"

    @extend_schema(responses={200: LocationSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = Location.objects.select_related("parent").all()
        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return Response(LocationSerializer(queryset, many=True).data)

    @extend_schema(request=LocationWriteSerializer, responses={200: LocationSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = LocationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        location = create_location(actor=request.user, request=request, data=serializer.validated_data)
        return Response(LocationSerializer(location).data)


class PlatformLocationDetailView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.catalog.manage"

    @extend_schema(request=LocationWriteSerializer, responses={200: LocationSerializer})
    def patch(self, request, location_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = LocationWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        location = update_location(
            actor=request.user,
            request=request,
            public_id=location_id,
            data=serializer.validated_data,
        )
        return Response(LocationSerializer(location).data)


class PlatformRouteListCreateView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.catalog.manage"

    @extend_schema(responses={200: RouteSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        queryset = Route.objects.select_related("origin_location", "destination_location").prefetch_related(
            "stops__location"
        )
        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return Response(RouteSerializer(queryset, many=True).data)

    @extend_schema(request=RouteWriteSerializer, responses={200: RouteSerializer})
    def post(self, request):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = RouteWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        route = create_route(actor=request.user, request=request, data=serializer.validated_data)
        route = Route.objects.select_related("origin_location", "destination_location").prefetch_related(
            "stops__location"
        ).get(pk=route.pk)
        return Response(RouteSerializer(route).data)


class PlatformRouteDetailView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.catalog.manage"

    @extend_schema(request=RouteWriteSerializer, responses={200: RouteSerializer})
    def patch(self, request, route_id: str):  # type: ignore[no-untyped-def]
        require_idempotency_key(request)
        serializer = RouteWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        route = update_route(
            actor=request.user,
            request=request,
            public_id=route_id,
            data=serializer.validated_data,
        )
        route = Route.objects.select_related("origin_location", "destination_location").prefetch_related(
            "stops__location"
        ).get(pk=route.pk)
        return Response(RouteSerializer(route).data)
