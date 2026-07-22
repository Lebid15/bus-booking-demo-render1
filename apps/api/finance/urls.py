from django.urls import path

from finance.views import (
    OfficeDisputeAppealView,
    OfficeDisputeListView,
    OfficeDisputeResponseView,
    OfficeSettlementListView,
    PlatformCommissionProfileDetailView,
    PlatformCommissionProfileListCreateView,
    PlatformDisputeCommandView,
    PlatformDisputeListView,
    PlatformSettlementCommandView,
    PlatformSettlementListCreateView,
)

urlpatterns = [
    path("platform/disputes", PlatformDisputeListView.as_view(), name="platform-disputes"),
    path(
        "platform/disputes/<str:dispute_id>/commands",
        PlatformDisputeCommandView.as_view(),
        name="platform-dispute-commands",
    ),
    path("office/disputes", OfficeDisputeListView.as_view(), name="office-disputes"),
    path(
        "office/disputes/<str:dispute_id>/respond", OfficeDisputeResponseView.as_view(), name="office-dispute-respond"
    ),
    path("office/disputes/<str:dispute_id>/appeal", OfficeDisputeAppealView.as_view(), name="office-dispute-appeal"),
    path("office/settlements", OfficeSettlementListView.as_view(), name="office-settlements"),
    path("platform/settlements", PlatformSettlementListCreateView.as_view(), name="platform-settlements"),
    path(
        "platform/settlements/<str:settlement_id>/commands",
        PlatformSettlementCommandView.as_view(),
        name="platform-settlement-commands",
    ),
    path(
        "platform/commission-profiles",
        PlatformCommissionProfileListCreateView.as_view(),
        name="platform-commission-profiles",
    ),
    path(
        "platform/commission-profiles/<str:profile_id>",
        PlatformCommissionProfileDetailView.as_view(),
        name="platform-commission-profile-detail",
    ),
]
