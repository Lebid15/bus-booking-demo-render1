from django.urls import path

from trips.views import (
    OfficeTripCommandView,
    OfficeTripDetailView,
    OfficeTripListCreateView,
    OfficeTripSeatMapView,
    OfficeTripVehicleReallocationApplyView,
    OfficeTripVehicleReallocationPreviewView,
    PlatformTripInterruptionBookingView,
    PlatformTripInterruptionCloseView,
    PublicTripChangeResponseView,
    PublicTripDetailView,
    PublicTripSearchView,
    PublicTripSeatMapView,
)

urlpatterns = [
    path(
        "office/trips/<str:trip_id>/vehicle-change/preview",
        OfficeTripVehicleReallocationPreviewView.as_view(),
        name="office-trip-vehicle-preview",
    ),
    path(
        "office/trips/<str:trip_id>/vehicle-change/apply",
        OfficeTripVehicleReallocationApplyView.as_view(),
        name="office-trip-vehicle-apply",
    ),
    path(
        "public/bookings/<str:pnr>/trip-changes/<str:change_id>/respond",
        PublicTripChangeResponseView.as_view(),
        name="public-trip-change-response",
    ),
    path(
        "platform/trips/<str:trip_id>/interruption/bookings",
        PlatformTripInterruptionBookingView.as_view(),
        name="platform-trip-interruption-booking",
    ),
    path(
        "platform/trips/<str:trip_id>/interruption/close",
        PlatformTripInterruptionCloseView.as_view(),
        name="platform-trip-interruption-close",
    ),
    path("public/trips/search", PublicTripSearchView.as_view(), name="public-trip-search"),
    path("public/trips/<str:trip_id>", PublicTripDetailView.as_view(), name="public-trip-detail"),
    path("public/trips/<str:trip_id>/seats", PublicTripSeatMapView.as_view(), name="public-trip-seats"),
    path("office/trips", OfficeTripListCreateView.as_view(), name="office-trips"),
    path("office/trips/<str:trip_id>", OfficeTripDetailView.as_view(), name="office-trip-detail"),
    path(
        "office/trips/<str:trip_id>/commands",
        OfficeTripCommandView.as_view(),
        name="office-trip-command",
    ),
    path(
        "office/trips/<str:trip_id>/seat-map",
        OfficeTripSeatMapView.as_view(),
        name="office-trip-seat-map",
    ),
]
