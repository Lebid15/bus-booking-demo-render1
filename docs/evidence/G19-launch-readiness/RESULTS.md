# G19 Launch Readiness Evidence

## Outcome

- Release classification: **v0.19.1 RC2**.
- Functional scope: **19/19 epics, 103/103 acceptance criteria**.
- PostgreSQL 18.4 full suite: **139/139 PASS**.
- SQLite compatibility suite: **135 PASS / 4 PostgreSQL-only SKIP**.
- PostgreSQL, Redis, Celery Worker, Celery Beat, API Smoke, logical restore and PITR: **PASS**.

## Quality gates

| Gate | Result | Evidence |
|---|---|---|
| PostgreSQL 18 full suite | 139/139 PASS | `pytest-postgresql18.log`, `pytest-postgresql18.xml` |
| SQLite compatibility | 135 PASS / 4 expected SKIP | `pytest-sqlite.log`, `pytest-sqlite.xml` |
| Fresh PostgreSQL migration | PASS | `migrate-postgresql18-fresh.log` |
| Staging-schema migration | PASS | `staging-migrate-postgresql18.log` |
| Permission seed | PASS — 43 permissions | `staging-seed-foundation.log` |
| Notification seed | PASS — 120 templates | `staging-seed-notifications.log` |
| Django check | PASS | `django-check.log` |
| Production deploy check | PASS | `django-deploy-check.log` |
| Migration drift | PASS | `migration-drift.log` |
| Ruff | PASS | `ruff.log` |
| Mypy strict | PASS — 175 source files | `mypy-final.log` |
| Bandit | PASS | `bandit.log` |
| OpenAPI | PASS — 132 paths / 157 operations | `openapi-generated.yaml`, `openapi.log` |
| Frontend lint | PASS | `frontend-lint.log` |
| TypeScript | PASS | `frontend-typecheck.log` |
| UX static contract | 7/7 PASS | `ux-contract.log` |
| Next.js Production build | PASS — 40 routes | `frontend-build.log` |
| npm audit | 0 vulnerabilities in successful run; later registry repeat returned 503 with unchanged dependencies | `npm-audit.log`, `npm-audit-final.log` |
| API runtime Smoke | PASS with payload validation | `api-smoke.log`, `api-smoke-details.log` |
| Concurrent API smoke | 600/600 HTTP 200, concurrency 30 | `local-api-load-smoke.log` |
| Production Web/API runtime | Five key routes HTTP 200 with RTL | `frontend-production-smoke.log`, `frontend-production-runtime.log` |
| Redis/Celery runtime | PASS | `celery-runtime-ping.log`, `celery-worker-runtime.log`, `celery-beat-runtime.log` |
| Logical backup/restore | PASS | `backup-restore-drill.log`, `backups/` |
| PostgreSQL PITR | PASS | `pitr-drill.log` |
| Container/runtime contract | 8/8 PASS | `container-runtime-contract.log` |
| Source changeset | 4 added / 23 modified / 0 deleted | `SOURCE_CHANGESET.md` |
| Orderly service shutdown | PASS | `service-shutdown.log` |
| pip-audit | BLOCKED by PyPI DNS | `pip-audit.log` |

## Database and concurrency corrections

- psycopg 3-safe deferred ledger trigger migration;
- PostgreSQL-safe row locking on nullable joins;
- PostgreSQL-safe subscription locking without `DISTINCT`;
- Idempotency scope migration from 30 to 80 characters;
- transaction-aware concurrency test harness;
- UUID-safe audit redaction with regression coverage;
- ASGI-safe database connection lifetime preventing PostgreSQL client exhaustion;
- Production Uvicorn/Next container commands instead of development servers;
- bounded Next.js build workers for stable high-core CI builds.

## Backup evidence

- Logical backup SHA-256: `d60e4d81bc2f70b31fb7c852a43643a66436dfea4a30a575493bf65212b8b456`.
- Logical backup size: 830,584 bytes.
- Source/restored counts: 36 migrations, 43 permissions, 120 notification templates.
- PITR base backup: 707 ms.
- PITR restore to ready: 630 ms.
- The record deleted after the target timestamp was recovered successfully.

## External gates still open

- actual Staging deployment and observability integration;
- provider Sandboxes;
- private object storage and malware scanner;
- representative load, independent penetration and connected dependency audits;
- legal/commercial approvals;
- real-office pilot.
