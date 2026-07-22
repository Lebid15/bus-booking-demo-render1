from celery import shared_task  # type: ignore[import-untyped]

from subscriptions.services import process_due_subscriptions


@shared_task(name="subscriptions.process_due_subscriptions")  # type: ignore[misc]
def process_due_subscriptions_task() -> dict[str, int]:
    return process_due_subscriptions()
