from django.urls import path

from geography.views import (
    PlatformLocationDetailView,
    PlatformLocationListCreateView,
    PlatformRouteDetailView,
    PlatformRouteListCreateView,
    PublicLocationListView,
)

urlpatterns = [
    path("public/locations", PublicLocationListView.as_view(), name="public-locations"),
    path("platform/locations", PlatformLocationListCreateView.as_view(), name="platform-locations"),
    path(
        "platform/locations/<str:location_id>",
        PlatformLocationDetailView.as_view(),
        name="platform-location-detail",
    ),
    path("platform/routes", PlatformRouteListCreateView.as_view(), name="platform-routes"),
    path(
        "platform/routes/<str:route_id>",
        PlatformRouteDetailView.as_view(),
        name="platform-route-detail",
    ),
]
