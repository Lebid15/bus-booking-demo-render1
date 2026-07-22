#!/usr/bin/env bash
set -euo pipefail
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required}"
backup="${1:?backup dump path is required}"
sha256sum -c "$backup.sha256"
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$RESTORE_DATABASE_URL" "$backup"
