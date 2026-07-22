from __future__ import annotations

import uuid

import pytest
from django.test import override_settings
from django.utils import timezone

from bookings.models import Booking, SeatAssignment
from bookings.services import create_public_booking
from common.exceptions import DomainAPIException
from identity.models import User
from tickets.models import Ticket
from tickets.services import reissue_ticket_for_passenger, ticket_qr_data, verify_ticket_qr

from .test_e05_public_search_holds import _bookable_trip, _request
from .test_e06_booking_confirmation import _booking_payload, _hold
from .test_identity_foundation import bearer

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _confirmed_booking() -> tuple[Booking, dict[str, object]]:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key=f"e08-hold-{uuid.uuid4()}")
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers),
        idempotency_key=f"e08-booking-{uuid.uuid4()}",
        request=_request(key=f"e08-request-{uuid.uuid4()}"),
    )
    return Booking.objects.get(public_id=result["id"]), result


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_ac01_confirmed_guest_booking_issues_ticket_per_passenger() -> None:
    trip = _bookable_trip()
    seats = list(trip.seats.all()[:2])
    hold, passengers = _hold(trip, seats=seats, key="e08-multi-hold")
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers),
        idempotency_key="e08-multi-booking",
        request=_request(key="e08-multi-booking"),
    )

    booking = Booking.objects.get(public_id=result["id"])
    assert booking.tickets.filter(status=Ticket.Status.ACTIVE).count() == 2
    assert len(result["passengers"]) == 2
    for passenger in result["passengers"]:
        ticket = passenger["ticket"]
        assert ticket is not None
        assert ticket["version"] == 1
        assert ticket["status"] == Ticket.Status.ACTIVE
        assert str(ticket["qr_data"]).startswith("tq1.")
        assert verify_ticket_qr(str(ticket["qr_data"])).id == uuid.UUID(str(ticket["id"]))


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_awaiting_payment_booking_does_not_issue_active_ticket() -> None:
    trip = _bookable_trip()
    seat = trip.seats.first()
    assert seat is not None
    hold, passengers = _hold(trip, seats=[seat], key="e08-waiting-hold")
    result = create_public_booking(
        payload=_booking_payload(trip, hold, passengers, payment_method="manual_transfer"),
        idempotency_key="e08-waiting-booking",
        request=_request(key="e08-waiting-booking"),
    )
    booking = Booking.objects.get(public_id=result["id"])
    assert booking.status == Booking.Status.AWAITING_PAYMENT
    assert booking.tickets.count() == 0
    assert result["passengers"][0]["ticket"] is None


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_guest_manage_token_and_lookup_retrieve_ticket(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created = _confirmed_booking()
    managed = api_client.get(
        f"/v1/public/bookings/{booking.pnr}",
        {"manage_token": created["manage_token"]},
    )
    assert managed.status_code == 200
    assert managed.data["pnr"] == booking.pnr
    assert managed.data["passengers"][0]["ticket"]["status"] == Ticket.Status.ACTIVE

    looked_up = api_client.post(
        "/v1/public/bookings/lookup",
        {"pnr": booking.pnr.lower(), "contact_verifier": booking.contact_phone},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e08-lookup-good",
    )
    assert looked_up.status_code == 200
    assert looked_up.data["manage_token"] == created["manage_token"]
    assert looked_up.data["passengers"][0]["ticket"]["qr_data"].startswith("tq1.")


@override_settings(
    PUBLIC_HOLD_RATE_LIMIT=100,
    PUBLIC_BOOKING_RATE_LIMIT=100,
    PUBLIC_BOOKING_LOOKUP_RATE_LIMIT=2,
)
@pytest.mark.security
def test_e08_ac02_lookup_is_generic_and_rate_limited(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, _ = _confirmed_booking()
    wrong_contact = api_client.post(
        "/v1/public/bookings/lookup",
        {"pnr": booking.pnr, "contact_verifier": "+963999999999"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e08-lookup-wrong-contact",
        REMOTE_ADDR="198.51.100.80",
    )
    wrong_pnr = api_client.post(
        "/v1/public/bookings/lookup",
        {"pnr": "ZZZZZZZZ", "contact_verifier": booking.contact_phone},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e08-lookup-wrong-pnr",
        REMOTE_ADDR="198.51.100.80",
    )
    limited = api_client.post(
        "/v1/public/bookings/lookup",
        {"pnr": booking.pnr, "contact_verifier": booking.contact_phone},
        format="json",
        HTTP_IDEMPOTENCY_KEY="e08-lookup-limited",
        REMOTE_ADDR="198.51.100.80",
    )

    assert wrong_contact.status_code == 404
    assert wrong_pnr.status_code == 404
    assert wrong_contact.data["error"]["code"] == wrong_pnr.data["error"]["code"]
    assert wrong_contact.data["error"]["message"] == wrong_pnr.data["error"]["message"]
    assert limited.status_code == 429
    assert limited.data["error"]["code"] == "RATE_LIMITED"


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_ac03_reissue_revokes_old_qr_and_increments_version() -> None:
    booking, result = _confirmed_booking()
    passenger = booking.passengers.get()
    assignment = SeatAssignment.objects.get(passenger=passenger, status=SeatAssignment.Status.ACTIVE)
    old_ticket = Ticket.objects.get(passenger=passenger, status=Ticket.Status.ACTIVE)
    old_qr = str(result["passengers"][0]["ticket"]["qr_data"])

    passenger.full_name = "مسافر معدل"
    passenger.save(update_fields=["full_name"])
    replacement = reissue_ticket_for_passenger(
        passenger=passenger,
        seat_assignment=assignment,
        reason="passenger_details_changed",
    )

    old_ticket.refresh_from_db()
    assert old_ticket.status == Ticket.Status.REVOKED
    assert old_ticket.revoked_at is not None
    assert replacement.version_no == 2
    assert Ticket.objects.filter(passenger=passenger, status=Ticket.Status.ACTIVE).count() == 1
    with pytest.raises(DomainAPIException) as exc:
        verify_ticket_qr(old_qr)
    assert getattr(exc.value, "code", None) == "TICKET_QR_REVOKED"
    assert verify_ticket_qr(ticket_qr_data(replacement)).id == replacement.id


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_ac04_ticket_document_and_qr_are_available_without_email(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created = _confirmed_booking()
    ticket_id = created["passengers"][0]["ticket"]["id"]
    token = created["manage_token"]

    document = api_client.get(
        f"/v1/public/bookings/{booking.pnr}/tickets/{ticket_id}/document",
        {"manage_token": token},
    )
    qr = api_client.get(
        f"/v1/public/tickets/{ticket_id}/qr.svg",
        {"pnr": booking.pnr, "manage_token": token},
    )
    assert document.status_code == 200
    assert document["Content-Type"].startswith("text/html")
    assert booking.pnr.encode() in document.content
    assert "window.print" in document.content.decode()
    assert qr.status_code == 200
    assert qr["Content-Type"] == "image/svg+xml"
    assert b"<svg" in qr.content


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
def test_e08_ac05_verified_customer_links_guest_booking_without_copy(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created = _confirmed_booking()
    user = User.objects.create_user(
        full_name="صاحب الحجز",
        email=booking.contact_email,
        password="SecurePass!234",
    )
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email_verified_at"])
    login = api_client.post(
        "/v1/auth/login",
        {"identifier": user.email, "password": "SecurePass!234"},
        format="json",
    )
    bearer(api_client, login.data["access_token"])

    linked = api_client.post(
        "/v1/me/bookings/link",
        {"pnr": booking.pnr, "manage_token": created["manage_token"]},
        format="json",
    )
    mine = api_client.get("/v1/me/bookings")

    booking.refresh_from_db()
    assert linked.status_code == 200
    assert mine.status_code == 200
    assert booking.customer_user == user
    assert Booking.objects.filter(id=booking.id).count() == 1
    assert [item["pnr"] for item in mine.data] == [booking.pnr]


@override_settings(PUBLIC_HOLD_RATE_LIMIT=100, PUBLIC_BOOKING_RATE_LIMIT=100)
@pytest.mark.security
def test_e08_ticket_qr_is_tamper_evident_and_document_requires_manage_token(api_client) -> None:  # type: ignore[no-untyped-def]
    booking, created = _confirmed_booking()
    ticket_payload = created["passengers"][0]["ticket"]
    assert ticket_payload is not None
    ticket = Ticket.objects.get(id=ticket_payload["id"])
    qr_data = str(ticket_payload["qr_data"])
    assert bytes(ticket.qr_token_hash) != qr_data.encode()

    tampered = f"{qr_data[:-1]}{'A' if qr_data[-1] != 'A' else 'B'}"
    with pytest.raises(DomainAPIException) as exc:
        verify_ticket_qr(tampered)
    assert exc.value.code == "TICKET_QR_INVALID"

    unauthorized = api_client.get(
        f"/v1/public/bookings/{booking.pnr}/tickets/{ticket.id}/document",
        {"manage_token": "mb1_invalid"},
    )
    assert unauthorized.status_code == 404
    assert unauthorized.data["error"]["code"] == "RESOURCE_NOT_FOUND"
