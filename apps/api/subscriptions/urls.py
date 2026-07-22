from django.urls import path

from subscriptions.views import (
    OfficeAvailablePlansView,
    OfficeSubscriptionChangeRequestView,
    OfficeSubscriptionView,
    PlatformOfficeSubscriptionView,
    PlatformSubscriptionChangeCommandView,
    PlatformSubscriptionChangeListView,
    PlatformSubscriptionInvoiceCommandView,
    PlatformSubscriptionInvoiceListView,
    PlatformSubscriptionPlanDetailView,
    PlatformSubscriptionPlanListCreateView,
)

urlpatterns = [
    path("office/subscription", OfficeSubscriptionView.as_view(), name="office-subscription"),
    path("office/subscription-plans", OfficeAvailablePlansView.as_view(), name="office-subscription-plans"),
    path(
        "office/subscription/change-request",
        OfficeSubscriptionChangeRequestView.as_view(),
        name="office-subscription-change-request",
    ),
    path(
        "platform/subscription-plans",
        PlatformSubscriptionPlanListCreateView.as_view(),
        name="platform-subscription-plans",
    ),
    path(
        "platform/subscription-plans/<str:plan_id>",
        PlatformSubscriptionPlanDetailView.as_view(),
        name="platform-subscription-plan-detail",
    ),
    path(
        "platform/offices/<str:office_id>/subscription",
        PlatformOfficeSubscriptionView.as_view(),
        name="platform-office-subscription",
    ),
    path(
        "platform/subscription-invoices",
        PlatformSubscriptionInvoiceListView.as_view(),
        name="platform-subscription-invoices",
    ),
    path(
        "platform/subscription-invoices/<str:invoice_id>/commands",
        PlatformSubscriptionInvoiceCommandView.as_view(),
        name="platform-subscription-invoice-command",
    ),
    path(
        "platform/subscription-change-requests",
        PlatformSubscriptionChangeListView.as_view(),
        name="platform-subscription-change-requests",
    ),
    path(
        "platform/subscription-change-requests/<str:request_id>/commands",
        PlatformSubscriptionChangeCommandView.as_view(),
        name="platform-subscription-change-command",
    ),
]
