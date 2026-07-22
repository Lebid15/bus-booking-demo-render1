from django.urls import path

from payments.views import (
    OfficeCashPaymentView,
    OfficeManualPaymentQueueView,
    OfficeManualPaymentVerifyView,
    OfficeRefundCommandView,
    OfficeRefundListView,
    PaymentWebhookView,
    PlatformChargebackListView,
    PlatformRefundListView,
    PublicManualTransferSubmitView,
    PublicPaymentIntentCreateView,
)

urlpatterns = [
    path(
        "public/bookings/<str:pnr>/payments",
        PublicPaymentIntentCreateView.as_view(),
        name="public-payment-intent-create",
    ),
    path(
        "public/payment-intents/<str:intent_id>/manual-transfer",
        PublicManualTransferSubmitView.as_view(),
        name="public-manual-transfer-submit",
    ),
    path(
        "office/bookings/<str:booking_id>/payments/cash",
        OfficeCashPaymentView.as_view(),
        name="office-cash-payment",
    ),
    path(
        "office/manual-payments",
        OfficeManualPaymentQueueView.as_view(),
        name="office-manual-payment-queue",
    ),
    path(
        "office/manual-payments/<uuid:submission_id>/verify",
        OfficeManualPaymentVerifyView.as_view(),
        name="office-manual-payment-verify",
    ),
    path(
        "webhooks/payments/<str:provider_code>",
        PaymentWebhookView.as_view(),
        name="payment-webhook",
    ),
    path("office/refunds", OfficeRefundListView.as_view(), name="office-refunds"),
    path(
        "office/refunds/<uuid:refund_id>/commands",
        OfficeRefundCommandView.as_view(),
        name="office-refund-commands",
    ),
    path("platform/refunds", PlatformRefundListView.as_view(), name="platform-refunds"),
    path("platform/chargebacks", PlatformChargebackListView.as_view(), name="platform-chargebacks"),
]
