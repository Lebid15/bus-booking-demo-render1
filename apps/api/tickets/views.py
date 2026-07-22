from __future__ import annotations

import html
from io import BytesIO

import qrcode
import qrcode.image.svg
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from bookings.models import Booking
from bookings.services import manage_token_matches
from common.exceptions import DomainAPIException
from tickets.models import Ticket
from tickets.services import ticket_qr_data


def _authorized_ticket(*, pnr: str, ticket_id: str, manage_token: str) -> Ticket:
    booking = Booking.objects.filter(pnr=pnr.strip().upper()).first()
    if booking is None or not manage_token_matches(booking, manage_token):
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    ticket = (
        Ticket.objects.select_related(
            "booking__trip__route__origin_location",
            "booking__trip__route__destination_location",
            "booking__trip__office",
            "passenger",
            "seat_assignment__trip_seat",
        )
        .filter(id=ticket_id, booking=booking)
        .first()
    )
    if ticket is None:
        raise DomainAPIException("RESOURCE_NOT_FOUND")
    if ticket.status != Ticket.Status.ACTIVE:
        raise DomainAPIException("TICKET_QR_REVOKED")
    return ticket


def _qr_svg(qr_data: str) -> bytes:
    image = qrcode.make(qr_data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    output = BytesIO()
    image.save(output)
    return output.getvalue()


class PublicTicketQrView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[
            OpenApiParameter("pnr", str, required=True),
            OpenApiParameter("manage_token", str, required=True),
        ],
        responses={(200, "image/svg+xml"): bytes},
    )
    def get(self, request, ticket_id: str):  # type: ignore[no-untyped-def]
        ticket = _authorized_ticket(
            pnr=str(request.query_params.get("pnr", "")),
            ticket_id=ticket_id,
            manage_token=str(request.query_params.get("manage_token", "")),
        )
        return HttpResponse(_qr_svg(ticket_qr_data(ticket)), content_type="image/svg+xml")


class PublicTicketDocumentView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        parameters=[OpenApiParameter("manage_token", str, required=True)],
        responses={(200, "text/html"): bytes},
    )
    def get(self, request, pnr: str, ticket_id: str):  # type: ignore[no-untyped-def]
        token = str(request.query_params.get("manage_token", ""))
        ticket = _authorized_ticket(pnr=pnr, ticket_id=ticket_id, manage_token=token)
        booking = ticket.booking
        trip = booking.trip
        passenger = ticket.passenger
        seat = ticket.seat_assignment.trip_seat
        qr_svg = _qr_svg(ticket_qr_data(ticket)).decode()
        origin_name = html.escape(trip.route.origin_location.name_ar)
        destination_name = html.escape(trip.route.destination_location.name_ar)
        document = f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تذكرة {html.escape(booking.pnr)}</title>
<style>
body{{font-family:Arial,sans-serif;background:#f3f7f6;color:#17312d;padding:24px}}
.ticket{{max-width:760px;margin:auto;background:#fff;border:1px solid #cfe0dc;border-radius:24px;padding:28px}}
.grid{{display:grid;grid-template-columns:1fr 220px;gap:24px;align-items:center}}
.meta{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.meta div{{border:1px solid #e2ece9;border-radius:12px;padding:12px}}
small{{display:block;color:#60736f;margin-bottom:4px}} h1{{margin-top:0}} svg{{width:210px;height:210px}}
.actions{{margin-top:20px}} button{{padding:10px 18px;border:0;border-radius:10px;background:#0f766e;color:#fff}}
@media print{{body{{background:#fff;padding:0}}.ticket{{border:0}}.actions{{display:none}}}}
</style>
</head>
<body>
<article class="ticket">
<div class="grid">
<div>
<h1>تذكرة سفر</h1>
<p><strong>{origin_name}</strong> ← <strong>{destination_name}</strong></p>
<div class="meta">
<div><small>PNR</small><bdi dir="ltr">{html.escape(booking.pnr)}</bdi></div>
<div><small>المسافر</small>{html.escape(passenger.full_name)}</div>
<div><small>المقعد</small>{html.escape(seat.seat_code)}</div>
<div><small>الإصدار</small>{ticket.version_no}</div>
<div><small>المكتب</small>{html.escape(trip.office.trade_name)}</div>
<div><small>الانطلاق</small><bdi dir="ltr">{trip.scheduled_departure_at.isoformat()}</bdi></div>
</div>
</div>
<div aria-label="رمز QR للتذكرة">{qr_svg}</div>
</div>
<div class="actions"><button onclick="window.print()">طباعة أو حفظ PDF</button></div>
</article>
</body>
</html>"""
        response = HttpResponse(document, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = f'inline; filename="ticket-{booking.pnr}-{passenger.sequence_no}.html"'
        response["Cache-Control"] = "private, no-store"
        return response
