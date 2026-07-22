#!/usr/bin/env python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from tests.test_e05_public_search_holds import _bookable_trip

trip = _bookable_trip()
print(json.dumps({
    "trip_id": trip.public_id,
    "origin_id": trip.route.origin_location.public_id,
    "destination_id": trip.route.destination_location.public_id,
    "date": trip.scheduled_departure_at.astimezone().date().isoformat(),
}))
