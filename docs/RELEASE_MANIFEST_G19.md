# Release Manifest — G19 / v0.19.1 RC2

## Scope

This release does not add new product scope. It hardens the completed v4.0 implementation against PostgreSQL 18 and closes locally executable launch-readiness gates.

## Source changes

- `apps/api/continuity/views.py` — complete strict typing for continuity response schemas.
- `apps/api/finance/migrations/0002_ledger_balance_trigger.py` — psycopg 3-safe PL/pgSQL exception construction and integrity SQLSTATE.
- `apps/api/trips/services.py` — targeted row locking.
- `apps/api/trips/reallocation_services.py` — targeted row locking.
- `apps/api/payments/refund_services.py` — targeted row locking.
- `apps/api/support/services.py` — targeted row locking.
- `apps/api/securityops/services.py` — targeted row locking.
- `apps/api/notifications/services.py` — targeted row locking.
- `apps/api/subscriptions/services.py` — PostgreSQL-safe due/grace invoice selection.
- `apps/api/common/models.py` — widened Idempotency scope.
- `apps/api/common/migrations/0002_widen_idempotency_scope.py` — schema migration.
- `apps/api/auditlog/services.py` — UUID-safe card redaction.
- `apps/api/tests/test_e06_booking_confirmation.py` — correct transactional concurrency harness.
- `apps/api/tests/test_audit_redaction.py` — new redaction regressions.
- `scripts/smoke_release.sh` — strict 2xx and JSON payload checks.
- `apps/api/config/settings.py` — API release marker and ASGI-safe database connection lifetime.
- `apps/api/requirements.txt` — pinned Uvicorn Production server.
- `apps/api/Dockerfile` — Uvicorn multi-worker runtime instead of Django development server.
- `apps/web/Dockerfile` — built Next Production runtime instead of `next dev`.
- `apps/web/next.config.ts` — bounded page-data build workers.
- `docker-compose.yml` — Production server commands and immutable built application files.
- `.env.example` — database connection and worker controls.
- `scripts/check_python_dependencies.py` — project-scoped direct/transitive dependency consistency check.

## Verification

See `docs/evidence/G19-launch-readiness/RESULTS.md` and `docs/FINAL_CLOSURE_STATUS.md`.

## Known external dependencies

No payment, messaging, storage, scanner or Production secret is bundled in this package. Those integrations must be supplied and verified in the target Staging environment.
