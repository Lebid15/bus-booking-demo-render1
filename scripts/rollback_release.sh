#!/usr/bin/env bash
set -euo pipefail
previous="${1:?previous release reference is required}"
echo "Rollback requested to $previous"
echo "Run the environment-specific deployment rollback, then execute scripts/smoke_release.sh."
