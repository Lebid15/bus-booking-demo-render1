#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata
import sys
from collections import deque
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def requirement_lines(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-r "):
            continue
        requirements.append(Requirement(line))
    return requirements


def main() -> int:
    requirements_path = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/api/requirements.txt")
    installed = {
        canonicalize_name(dist.metadata["Name"]): dist
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    direct = requirement_lines(requirements_path)
    pending = deque(direct)
    checked: set[str] = set()
    errors: list[str] = []

    while pending:
        requirement = pending.popleft()
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        name = canonicalize_name(requirement.name)
        distribution = installed.get(name)
        if distribution is None:
            errors.append(f"missing: {requirement}")
            continue
        if requirement.specifier and distribution.version not in requirement.specifier:
            errors.append(f"version mismatch: {requirement}; installed={distribution.version}")
        if name in checked:
            continue
        checked.add(name)
        for dependency_text in distribution.requires or []:
            dependency = Requirement(dependency_text)
            if dependency.marker and not dependency.marker.evaluate({"extra": ""}):
                continue
            pending.append(dependency)

    if errors:
        print("Project dependency check: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Project dependency check: PASS "
        f"({len(direct)} direct requirements, {len(checked)} installed direct/transitive distributions)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
