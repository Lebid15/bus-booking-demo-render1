from celery import shared_task  # type: ignore[import-untyped]

from bookings.services import expire_due_holds


@shared_task(name="bookings.expire_seat_holds")  # type: ignore[misc]
def expire_seat_holds_task() -> int:
    return expire_due_holds()
