#!/usr/bin/env bash
set -euo pipefail

base="${1:-http://localhost:8000}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

curl_args=(--silent --show-error)
if [[ -n "${SMOKE_FORWARDED_PROTO:-}" ]]; then
  curl_args+=(--header "X-Forwarded-Proto: ${SMOKE_FORWARDED_PROTO}")
fi

request_json() {
  local name="$1"
  local path="$2"
  local output="$tmp_dir/${name}.json"
  local status
  status="$(curl "${curl_args[@]}" --output "$output" --write-out '%{http_code}' "$base$path")"
  if [[ ! "$status" =~ ^2[0-9][0-9]$ ]]; then
    echo "smoke: FAIL $path returned HTTP $status" >&2
    sed -n '1,20p' "$output" >&2 || true
    exit 1
  fi
  python -m json.tool "$output" >/dev/null
}

request_json live /health/live
request_json ready /health/ready
request_json locations /v1/public/locations

python - "$tmp_dir" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
live = json.loads((root / "live.json").read_text())
ready = json.loads((root / "ready.json").read_text())
locations = json.loads((root / "locations.json").read_text())

if live.get("status") != "ok" or live.get("service") != "bus-booking-api":
    raise SystemExit(f"smoke: FAIL unexpected liveness payload: {live!r}")

checks = ready.get("checks")
if ready.get("status") != "ok" or not isinstance(checks, dict) or any(value != "ok" for value in checks.values()):
    raise SystemExit(f"smoke: FAIL readiness payload is degraded: {ready!r}")

if not isinstance(locations, (dict, list)):
    raise SystemExit("smoke: FAIL locations payload is not a JSON object or array")
PY

echo "smoke: PASS"
