from django.urls import path

from securityops.views import (
    MyAccountDeletionView,
    MyDataExportView,
    PlatformLegalHoldListCreateView,
    PlatformLegalHoldReleaseView,
    PlatformRiskAssessmentListView,
    RiskChallengeVerifyView,
    UploadCompleteView,
    UploadIntentView,
)

urlpatterns = [
    path("files/upload-intents", UploadIntentView.as_view(), name="file-upload-intent"),
    path("files/<uuid:file_id>/complete", UploadCompleteView.as_view(), name="file-upload-complete"),
    path("me/data-export", MyDataExportView.as_view(), name="my-data-export"),
    path("me/delete-account", MyAccountDeletionView.as_view(), name="my-account-delete"),
    path(
        "public/risk-challenges/<uuid:challenge_id>/verify",
        RiskChallengeVerifyView.as_view(),
        name="risk-challenge-verify",
    ),
    path(
        "platform/risk-assessments",
        PlatformRiskAssessmentListView.as_view(),
        name="platform-risk-assessments",
    ),
    path("platform/legal-holds", PlatformLegalHoldListCreateView.as_view(), name="platform-legal-holds"),
    path(
        "platform/legal-holds/<uuid:hold_id>/release",
        PlatformLegalHoldReleaseView.as_view(),
        name="platform-legal-hold-release",
    ),
]
