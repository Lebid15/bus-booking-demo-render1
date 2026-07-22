from __future__ import annotations

from celery import shared_task  # type: ignore[import-untyped]

from payments.services import expire_due_unpaid_bookings, process_received_webhook_deliveries


@shared_task(name="payments.expire_due_unpaid_bookings")  # type: ignore[misc]
def expire_due_unpaid_bookings_task() -> int:
    return expire_due_unpaid_bookings()


@shared_task(name="payments.process_received_webhooks")  # type: ignore[misc]
def process_received_webhooks_task() -> int:
    return process_received_webhook_deliveries()
