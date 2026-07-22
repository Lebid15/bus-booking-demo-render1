from django.urls import path

from adminops.views import (
    OfficeReportsSummaryView,
    PlatformApprovalCommandView,
    PlatformApprovalListView,
    PlatformAuditView,
    PlatformOfficeDetailView,
    PlatformOfficeStatusView,
    PlatformOfficeViolationCommandView,
    PlatformOfficeViolationListCreateView,
    PlatformReportsSummaryView,
)

urlpatterns = [
    path("platform/approvals", PlatformApprovalListView.as_view()),
    path("platform/approvals/<str:approval_id>/commands", PlatformApprovalCommandView.as_view()),
    path("platform/offices/<str:office_id>", PlatformOfficeDetailView.as_view()),
    path("platform/offices/<str:office_id>/status", PlatformOfficeStatusView.as_view()),
    path("platform/offices/<str:office_id>/violations", PlatformOfficeViolationListCreateView.as_view()),
    path(
        "platform/offices/<str:office_id>/violations/<str:violation_id>/commands",
        PlatformOfficeViolationCommandView.as_view(),
    ),
    path("platform/audit-logs", PlatformAuditView.as_view()),
    path("platform/reports/summary", PlatformReportsSummaryView.as_view()),
    path("office/reports/summary", OfficeReportsSummaryView.as_view()),
]
