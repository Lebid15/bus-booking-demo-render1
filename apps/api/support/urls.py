from django.urls import path

from support.views import (
    OfficeRecoveryLookupView,
    OfficeSupportCaseListView,
    OfficeSupportMessageView,
    PlatformSupportCaseCommandView,
    PlatformSupportCaseListView,
    PlatformSupportMessageView,
    PublicBookingSupportCaseView,
)

urlpatterns = [
    path("public/bookings/<str:pnr>/support-cases", PublicBookingSupportCaseView.as_view(), name="public-support-case"),
    path("office/support-cases", OfficeSupportCaseListView.as_view(), name="office-support-cases"),
    path(
        "office/support-cases/<str:case_id>/messages",
        OfficeSupportMessageView.as_view(),
        name="office-support-messages",
    ),
    path(
        "office/trips/<str:trip_id>/recovery-lookup", OfficeRecoveryLookupView.as_view(), name="office-recovery-lookup"
    ),
    path("platform/support-cases", PlatformSupportCaseListView.as_view(), name="platform-support-cases"),
    path(
        "platform/support-cases/<str:case_id>/messages",
        PlatformSupportMessageView.as_view(),
        name="platform-support-messages",
    ),
    path(
        "platform/support-cases/<str:case_id>/commands",
        PlatformSupportCaseCommandView.as_view(),
        name="platform-support-command",
    ),
]
