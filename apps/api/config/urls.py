from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from common.views import live, ready

urlpatterns = [
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("v1/", include("identity.urls")),
    path("v1/", include("organizations.urls")),
    path("v1/", include("geography.urls")),
    path("v1/", include("fleet.urls")),
    path("v1/", include("policies.urls")),
    path("v1/", include("trips.urls")),
    path("v1/", include("bookings.urls")),
    path("v1/", include("tickets.urls")),
    path("v1/", include("boarding.urls")),
    path("v1/", include("support.urls")),
    path("v1/", include("payments.urls")),
    path("v1/", include("finance.urls")),
    path("v1/", include("adminops.urls")),
    path("v1/", include("notifications.urls")),
    path("v1/", include("securityops.urls")),
    path("v1/", include("subscriptions.urls")),
    path("v1/", include("continuity.urls")),
]
