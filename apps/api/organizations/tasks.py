from __future__ import annotations

from celery import shared_task  # type: ignore[import-untyped]

from organizations.services import activate_due_payout_accounts


@shared_task(name="organizations.activate_due_payout_accounts")  # type: ignore[misc]
def activate_due_payout_accounts_task() -> int:
    return activate_due_payout_accounts()
