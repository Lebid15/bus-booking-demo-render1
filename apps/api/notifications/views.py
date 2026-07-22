from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from auditlog.services import record_audit
from common.exceptions import DomainAPIException
from common.idempotency import begin_idempotency, complete_idempotency
from common.requests import require_idempotency_key
from identity.models import User
from notifications.models import Notification, NotificationDelivery, NotificationPreference, PushSubscription
from notifications.serializers import (
    NotificationDeliverySerializer,
    NotificationPreferenceBulkSerializer,
    NotificationPreferenceSerializer,
    NotificationSerializer,
    PushSubscriptionSerializer,
    PushSubscriptionWriteSerializer,
)
from notifications.services import register_push_subscription, update_preferences
from organizations.permissions import HasOfficeContext, HasPlatformAccess


class MeNotificationListView(APIView):
    @extend_schema(
        parameters=[OpenApiParameter("unread", bool, required=False)],
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        queryset = Notification.objects.select_related("template", "booking").filter(
            recipient_type=Notification.RecipientType.USER,
            recipient_id=user.id,
            template__channel="in_app",
        )
        if request.query_params.get("unread") in {"1", "true", "True"}:
            queryset = queryset.filter(read_at__isnull=True)
        return Response(NotificationSerializer(queryset[:200], many=True).data)


class MeNotificationReadView(APIView):
    @extend_schema(request=None, responses={200: NotificationSerializer})
    def post(self, request: Request, notification_id: str) -> Response:
        user = cast(User, request.user)
        try:
            notification = Notification.objects.select_related("template", "booking").get(
                id=notification_id,
                recipient_type=Notification.RecipientType.USER,
                recipient_id=user.id,
                template__channel="in_app",
            )
        except (Notification.DoesNotExist, ValueError) as exc:
            raise DomainAPIException("RESOURCE_NOT_FOUND") from exc
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


class MeNotificationPreferenceView(APIView):
    @extend_schema(responses={200: NotificationPreferenceSerializer(many=True)})
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        rows = NotificationPreference.objects.filter(user=user).order_by("event_type", "channel")
        return Response(NotificationPreferenceSerializer(rows, many=True).data)

    @extend_schema(
        request=NotificationPreferenceBulkSerializer, responses={200: NotificationPreferenceSerializer(many=True)}
    )
    def patch(self, request: Request) -> Response:
        serializer = NotificationPreferenceBulkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = cast(dict[str, Any], serializer.validated_data)
        raw_rows = cast(list[dict[str, object]], payload["preferences"])
        user = cast(User, request.user)
        rows = update_preferences(user=user, rows=raw_rows)
        return Response(NotificationPreferenceSerializer(rows, many=True).data)


class MePushSubscriptionView(APIView):
    @extend_schema(responses={200: PushSubscriptionSerializer(many=True)})
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        rows = PushSubscription.objects.filter(user=user).order_by("-created_at")
        return Response(PushSubscriptionSerializer(rows, many=True).data)

    @extend_schema(request=PushSubscriptionWriteSerializer, responses={200: PushSubscriptionSerializer})
    def post(self, request: Request) -> Response:
        serializer = PushSubscriptionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = cast(User, request.user)
        subscription = register_push_subscription(
            user=user,
            token=str(serializer.validated_data["token"]),
            platform=str(serializer.validated_data["platform"]),
        )
        return Response(PushSubscriptionSerializer(subscription).data)


class OfficeNotificationListView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.notification.view"

    @extend_schema(responses={200: NotificationSerializer(many=True)})
    def get(self, request: Request) -> Response:
        office = request.office_context.office
        rows = Notification.objects.select_related("template", "booking").filter(
            recipient_type=Notification.RecipientType.OFFICE,
            recipient_id=office.id,
            template__channel="in_app",
        )[:200]
        return Response(NotificationSerializer(rows, many=True).data)


class PlatformNotificationDeliveryListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.notification.manage"

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, required=False),
            OpenApiParameter("channel", str, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        queryset = NotificationDelivery.objects.select_related("notification", "notification__template").order_by(
            "-created_at"
        )
        if status := request.query_params.get("status"):
            queryset = queryset.filter(status=status)
        if channel := request.query_params.get("channel"):
            queryset = queryset.filter(channel=channel)
        rows = list(queryset[:200])
        return Response(
            {
                "results": [
                    {
                        **cast(dict[str, Any], NotificationDeliverySerializer(row).data),
                        "notification": cast(dict[str, Any], NotificationSerializer(row.notification).data),
                    }
                    for row in rows
                ]
            }
        )


class PlatformNotificationDeliveryRetryView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.notification.manage"

    @extend_schema(request=None, responses={200: NotificationDeliverySerializer})
    @transaction.atomic
    def post(self, request: Request, delivery_id: str) -> Response:
        try:
            delivery = (
                NotificationDelivery.objects.select_for_update().select_related("notification").get(id=delivery_id)
            )
        except (NotificationDelivery.DoesNotExist, ValueError) as exc:
            raise DomainAPIException("RESOURCE_NOT_FOUND") from exc
        key = require_idempotency_key(request)
        idem, replay = begin_idempotency(
            scope_type="notification_delivery_retry",
            scope_id=delivery.id,
            key=key,
            payload={"delivery_id": str(delivery.id)},
        )
        if replay is not None:
            return Response(replay)
        latest = (
            NotificationDelivery.objects.filter(notification=delivery.notification, channel=delivery.channel)
            .order_by("-attempt_no")
            .first()
        )
        if latest is None:
            raise DomainAPIException("RESOURCE_NOT_FOUND")
        retry, _ = NotificationDelivery.objects.get_or_create(
            notification=delivery.notification,
            channel=delivery.channel,
            attempt_no=latest.attempt_no + 1,
            defaults={
                "destination_hash": latest.destination_hash,
                "destination_ciphertext": latest.destination_ciphertext,
                "status": NotificationDelivery.Status.QUEUED,
                "next_attempt_at": timezone.now(),
            },
        )
        record_audit(
            action="platform.notification.delivery.retry",
            object_type="notification_delivery",
            object_id=retry.id,
            actor_user=cast(User, request.user),
            office_id=delivery.notification.booking.office_id if delivery.notification.booking else None,
            request=request,
            after={"attempt_no": retry.attempt_no, "channel": retry.channel},
        )
        response = cast(dict[str, Any], NotificationDeliverySerializer(retry).data)
        complete_idempotency(idem, response)
        return Response(response)
