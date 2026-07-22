#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "spec-v4.0"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def count_csv(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def main() -> None:
    if not SPEC.is_dir():
        fail("specification directory is missing")

    verified = 0
    for line in (SPEC / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        target = SPEC / relative
        if not target.is_file():
            fail(f"missing specification file: {relative}")
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            fail(f"checksum mismatch: {relative}")
        verified += 1

    manifest = read_json(SPEC / "machine" / "project_manifest.json")
    validation = read_json(SPEC / "machine" / "validation_report.json")
    for json_file in sorted((SPEC / "machine").glob("*.json")):
        read_json(json_file)

    openapi = yaml.safe_load((SPEC / "11_API" / "openapi.yaml").read_text(encoding="utf-8"))
    if not isinstance(openapi, dict) or "paths" not in openapi:
        fail("OpenAPI document has no paths")

    operation_names = {"get", "post", "put", "patch", "delete", "options", "head"}
    api_paths = len(openapi["paths"])
    api_operations = sum(
        1 for operations in openapi["paths"].values() for method in operations if method in operation_names
    )
    ddl = (SPEC / "04_DOMAIN" / "postgresql_schema.sql").read_text(encoding="utf-8")
    tables = len(re.findall(r"^CREATE TABLE\s+", ddl, flags=re.MULTILINE))
    acceptance = count_csv(SPEC / "machine" / "epic_acceptance.csv")
    screens = count_csv(SPEC / "machine" / "screen_catalog.csv")

    actual_stats = {
        "tables": tables,
        "acceptance": acceptance,
        "api_paths": api_paths,
        "api_operations": api_operations,
        "screens": screens,
    }
    for key, actual in actual_stats.items():
        expected = manifest["stats"][key]
        if actual != expected:
            fail(f"manifest statistic mismatch for {key}: expected {expected}, got {actual}")

    checks = validation.get("checks", {})
    if isinstance(checks, dict):
        failed_checks = {name: result for name, result in checks.items() if result not in {"PASS", "passed", True}}
    else:
        failed_checks = [
            check for check in checks if not isinstance(check, dict) or check.get("status") not in {"PASS", "passed", True}
        ]
    if failed_checks:
        fail(f"upstream validation report contains failed checks: {failed_checks}")

    report = {
        "package": manifest["package"],
        "version": manifest["version"],
        "status": manifest["status"],
        "checksums_verified": verified,
        "stats": actual_stats,
        "result": "PASS",
    }
    output = ROOT / "docs" / "evidence" / "G0-foundation" / "spec-validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
