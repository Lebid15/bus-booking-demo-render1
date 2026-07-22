from django.urls import path

from organizations.views import (
    OfficeBranchDetailView,
    OfficeBranchListCreateView,
    OfficeContextView,
    OfficePayoutAccountApproveView,
    OfficePayoutAccountListCreateView,
    OfficeStaffDetailView,
    OfficeStaffListCreateView,
    OfficeVerificationCommandView,
    OfficeVerificationDocumentListCreateView,
    OfficeVerificationView,
    PlatformOfficeDocumentReviewView,
    PlatformOfficeListView,
    PlatformOfficeVerificationCommandView,
)

urlpatterns = [
    path("office/context", OfficeContextView.as_view(), name="office-context"),
    path("office/branches", OfficeBranchListCreateView.as_view(), name="office-branches"),
    path("office/branches/<str:branch_id>", OfficeBranchDetailView.as_view(), name="office-branch-detail"),
    path("office/staff", OfficeStaffListCreateView.as_view(), name="office-staff"),
    path("office/staff/<str:membership_id>", OfficeStaffDetailView.as_view(), name="office-staff-detail"),
    path("office/verification", OfficeVerificationView.as_view(), name="office-verification"),
    path(
        "office/verification/commands",
        OfficeVerificationCommandView.as_view(),
        name="office-verification-command",
    ),
    path(
        "office/verification/documents",
        OfficeVerificationDocumentListCreateView.as_view(),
        name="office-verification-documents",
    ),
    path("office/payout-accounts", OfficePayoutAccountListCreateView.as_view(), name="office-payout-accounts"),
    path(
        "office/payout-accounts/<uuid:account_id>/approve",
        OfficePayoutAccountApproveView.as_view(),
        name="office-payout-account-approve",
    ),
    path("platform/offices", PlatformOfficeListView.as_view(), name="platform-offices"),
    path(
        "platform/offices/<str:office_id>/verification/commands",
        PlatformOfficeVerificationCommandView.as_view(),
        name="platform-office-verification-command",
    ),
    path(
        "platform/offices/<str:office_id>/documents/<str:document_id>",
        PlatformOfficeDocumentReviewView.as_view(),
        name="platform-office-document-review",
    ),
]
