#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:=./backups}"
mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
file="$BACKUP_DIR/bus-booking-$stamp.dump"
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" > "$file"
sha256sum "$file" > "$file.sha256"
echo "$file"
