from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.django_db


def test_liveness_and_request_id(api_client):  # type: ignore[no-untyped-def]
    request_id = str(uuid.uuid4())
    response = api_client.get("/health/live", HTTP_X_REQUEST_ID=request_id)
    assert response.status_code == 200
    assert response["X-Request-ID"] == request_id
    assert response.data["status"] == "ok"


def test_readiness_checks_database_and_cache(api_client):  # type: ignore[no-untyped-def]
    response = api_client.get("/health/ready")
    assert response.status_code == 200
    assert response.data["checks"] == {"database": "ok", "cache": "ok", "continuity": "ok"}


def test_invalid_request_id_is_replaced(api_client):  # type: ignore[no-untyped-def]
    response = api_client.get("/health/live", HTTP_X_REQUEST_ID="not-a-uuid")
    assert response.status_code == 200
    assert uuid.UUID(response["X-Request-ID"])
