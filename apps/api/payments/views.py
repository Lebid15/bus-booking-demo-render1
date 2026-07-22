from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import DomainAPIException
from common.requests import require_idempotency_key
from organizations.permissions import HasOfficeContext, HasPlatformAccess
from payments.refund_services import (
    command_refund,
    list_chargebacks,
    list_office_refunds,
    list_platform_refunds,
)
from payments.serializers import (
    ChargebackSerializer,
    CreatePaymentIntentSerializer,
    ManualPaymentDecisionSerializer,
    ManualPaymentQueueItemSerializer,
    ManualTransferSerializer,
    OfficeCashPaymentSerializer,
    PaymentIntentSerializer,
    PaymentWebhookRequestSerializer,
    RefundCommandSerializer,
    RefundSerializer,
    WebhookResponseSerializer,
)
from payments.services import (
    create_public_payment_intent,
    list_manual_payment_queue,
    receive_payment_webhook,
    record_office_cash_payment,
    submit_manual_transfer,
    verify_manual_payment,
    webhook_signature_valid,
)


class PublicPaymentIntentCreateView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[OpenApiParameter("manage_token", str, required=True)],
        request=CreatePaymentIntentSerializer,
        responses={200: PaymentIntentSerializer},
    )
    def post(self, request, pnr: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        manage_token = str(request.query_params.get("manage_token", ""))
        if not manage_token:
            raise DomainAPIException("AUTH_REQUIRED")
        serializer = CreatePaymentIntentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = create_public_payment_intent(
            pnr=pnr,
            manage_token=manage_token,
            idempotency_key=key,
            **serializer.validated_data,
        )
        return Response(PaymentIntentSerializer(response).data)


class PublicManualTransferSubmitView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=ManualTransferSerializer, responses={200: PaymentIntentSerializer})
    def post(self, request, intent_id: str):  # type: ignore[no-untyped-def]
        serializer = ManualTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = submit_manual_transfer(
            intent_id=intent_id,
            idempotency_key=require_idempotency_key(request),
            **serializer.validated_data,
        )
        return Response(PaymentIntentSerializer(response).data)


class OfficeCashPaymentView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.payment.confirm_manual"

    @extend_schema(request=OfficeCashPaymentSerializer, responses={200: PaymentIntentSerializer})
    def post(self, request, booking_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = OfficeCashPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = record_office_cash_payment(
            context=request.office_context,
            actor=request.user,
            request=request,
            booking_id=booking_id,
            idempotency_key=key,
            **serializer.validated_data,
        )
        return Response(PaymentIntentSerializer(response).data)


class OfficeManualPaymentQueueView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.finance.view"

    @extend_schema(responses={200: ManualPaymentQueueItemSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        response = list_manual_payment_queue(context=request.office_context)
        return Response(ManualPaymentQueueItemSerializer(response, many=True).data)  # type: ignore[arg-type]


class OfficeManualPaymentVerifyView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.payment.confirm_manual"

    @extend_schema(request=ManualPaymentDecisionSerializer, responses={200: PaymentIntentSerializer})
    def post(self, request, submission_id: str):  # type: ignore[no-untyped-def]
        key = require_idempotency_key(request)
        serializer = ManualPaymentDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = verify_manual_payment(
            context=request.office_context,
            actor=request.user,
            request=request,
            submission_id=submission_id,
            idempotency_key=key,
            **serializer.validated_data,
        )
        return Response(PaymentIntentSerializer(response).data)


class PaymentWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(request=PaymentWebhookRequestSerializer, responses={200: WebhookResponseSerializer})
    def post(self, request, provider_code: str):  # type: ignore[no-untyped-def]
        signature = str(request.headers.get("X-Payment-Signature", ""))
        if not webhook_signature_valid(payload_bytes=request.body, signature=signature):
            raise DomainAPIException("PAYMENT_WEBHOOK_INVALID")
        serializer = PaymentWebhookRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receive_payment_webhook(
            provider_code=provider_code,
            payload=serializer.validated_data,
            raw_payload=request.body,
        )
        return Response(WebhookResponseSerializer({"received": True}).data)


class OfficeRefundListView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.refund.view"

    @extend_schema(responses={200: RefundSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        response = list_office_refunds(
            context=request.office_context,
            status_filter=request.query_params.get("status"),
        )
        return Response(RefundSerializer(response, many=True).data)  # type: ignore[arg-type]


class OfficeRefundCommandView(APIView):
    permission_classes = [HasOfficeContext]
    required_permission = "office.refund.manage"

    @extend_schema(request=RefundCommandSerializer, responses={200: RefundSerializer})
    def post(self, request, refund_id):  # type: ignore[no-untyped-def]
        serializer = RefundCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        command = str(data.pop("command"))
        response = command_refund(
            refund_id=refund_id,
            command=command,
            actor=request.user,
            request=request,
            idempotency_key=require_idempotency_key(request),
            data=data,
            context=request.office_context,
        )
        return Response(RefundSerializer(response).data)


class PlatformRefundListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.refund.view"

    @extend_schema(responses={200: RefundSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        response = list_platform_refunds(
            status_filter=request.query_params.get("status"),
            office_id=request.query_params.get("office_id"),
        )
        return Response(RefundSerializer(response, many=True).data)  # type: ignore[arg-type]


class PlatformChargebackListView(APIView):
    permission_classes = [HasPlatformAccess]
    required_permission = "platform.chargeback.view"

    @extend_schema(responses={200: ChargebackSerializer(many=True)})
    def get(self, request):  # type: ignore[no-untyped-def]
        response = list_chargebacks(status_filter=request.query_params.get("status"))
        return Response(ChargebackSerializer(response, many=True).data)  # type: ignore[arg-type]
