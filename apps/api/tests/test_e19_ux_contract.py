from __future__ import annotations

import pytest

from trips.public_services import get_public_trip

from .test_e05_public_search_holds import _bookable_trip

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_e19_ac05_public_trip_exposes_versioned_policy_summaries_without_full_legal_text() -> None:
    trip = _bookable_trip()
    _, payload = get_public_trip(trip.public_id)

    summaries = payload["policy_summaries"]
    assert isinstance(summaries, list)
    assert len(summaries) == 3
    assert {item["policy_type"] for item in summaries} == {"boarding", "cancellation", "payment"}
    assert all(item["id"] and item["code"] and item["version_no"] for item in summaries)
    assert all("content_markdown" not in item for item in summaries)
