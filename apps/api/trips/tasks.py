from celery import shared_task  # type: ignore[import-untyped]

from trips.services import open_due_trip_bookings


@shared_task(name="trips.open_due_bookings")  # type: ignore[misc]
def open_due_bookings_task() -> int:
    return open_due_trip_bookings()
