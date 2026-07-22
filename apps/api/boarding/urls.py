from django.urls import path

from boarding.views import (
    OfficeBoardingCommandView,
    OfficeManifestView,
    OfficeOfflinePackageView,
    OfficeOfflineSyncView,
)

urlpatterns = [
    path("office/trips/<str:trip_id>/boarding", OfficeBoardingCommandView.as_view(), name="office-boarding"),
    path("office/trips/<str:trip_id>/manifest", OfficeManifestView.as_view(), name="office-manifest"),
    path(
        "office/trips/<str:trip_id>/offline-package",
        OfficeOfflinePackageView.as_view(),
        name="office-offline-package",
    ),
    path(
        "office/trips/<str:trip_id>/offline-sync",
        OfficeOfflineSyncView.as_view(),
        name="office-offline-sync",
    ),
]
