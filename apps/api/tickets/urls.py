from django.urls import path

from tickets.views import PublicTicketDocumentView, PublicTicketQrView

urlpatterns = [
    path(
        "public/bookings/<str:pnr>/tickets/<str:ticket_id>/document",
        PublicTicketDocumentView.as_view(),
        name="public-ticket-document",
    ),
    path(
        "public/tickets/<str:ticket_id>/qr.svg",
        PublicTicketQrView.as_view(),
        name="public-ticket-qr",
    ),
]
