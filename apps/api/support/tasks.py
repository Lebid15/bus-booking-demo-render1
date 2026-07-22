from celery import shared_task  # type: ignore[import-untyped]

from support.services import escalate_overdue_support_cases


@shared_task(name="support.escalate_overdue_cases")  # type: ignore[misc]
def escalate_overdue_cases_task() -> int:
    return escalate_overdue_support_cases()
