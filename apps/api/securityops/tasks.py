from celery import shared_task  # type: ignore[import-untyped]

from securityops.services import process_retention_requests


@shared_task(name="securityops.process_retention_requests")  # type: ignore[misc]
def process_retention_requests_task() -> dict[str, int]:
    return process_retention_requests()
