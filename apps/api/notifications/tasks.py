from celery import shared_task  # type: ignore[import-untyped]

from notifications.services import deliver_due_notifications, dispatch_outbox_events


@shared_task(name="notifications.dispatch_outbox_events")  # type: ignore[misc]
def dispatch_outbox_events_task() -> int:
    return dispatch_outbox_events(limit=200)


@shared_task(name="notifications.deliver_due_notifications")  # type: ignore[misc]
def deliver_due_notifications_task() -> int:
    return deliver_due_notifications(limit=200)
