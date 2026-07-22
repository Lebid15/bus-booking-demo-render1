from celery import shared_task  # type: ignore[import-untyped]

from boarding.services import mark_due_no_shows


@shared_task(name="boarding.mark_due_no_shows")  # type: ignore[misc]
def mark_due_no_shows_task() -> int:
    return mark_due_no_shows()
