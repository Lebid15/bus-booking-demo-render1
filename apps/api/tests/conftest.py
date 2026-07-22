from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_cache():  # type: ignore[no-untyped-def]
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()
