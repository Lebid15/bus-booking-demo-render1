from django.urls import path

from bookings.views import (
    MyBookingLinkView,
    MyBookingsListView,
    OfficeBookingCommandView,
    PublicBookingCancellationQuoteView,
    PublicBookingCancelView,
    PublicBookingCreateView,
    PublicBookingDetailView,
    PublicBookingLookupView,
    PublicSeatHoldCreateView,
    PublicSeatHoldReleaseView,
)

urlpatterns = [
    path("public/bookings", PublicBookingCreateView.as_view(), name="public-booking-create"),
    path("public/bookings/lookup", PublicBookingLookupView.as_view(), name="public-booking-lookup"),
    path("public/bookings/<str:pnr>", PublicBookingDetailView.as_view(), name="public-booking-detail"),
    path(
        "public/bookings/<str:pnr>/cancellation-quote",
        PublicBookingCancellationQuoteView.as_view(),
        name="public-booking-cancellation-quote",
    ),
    path(
        "public/bookings/<str:pnr>/cancel",
        PublicBookingCancelView.as_view(),
        name="public-booking-cancel",
    ),
    path("me/bookings", MyBookingsListView.as_view(), name="my-bookings"),
    path("me/bookings/link", MyBookingLinkView.as_view(), name="my-booking-link"),
    path(
        "office/bookings/<str:booking_id>/commands",
        OfficeBookingCommandView.as_view(),
        name="office-booking-commands",
    ),
    path("public/trips/<str:trip_id>/seat-holds", PublicSeatHoldCreateView.as_view(), name="public-seat-holds"),
    path(
        "public/seat-holds/<str:hold_token>/release",
        PublicSeatHoldReleaseView.as_view(),
        name="public-seat-hold-release",
    ),
]
