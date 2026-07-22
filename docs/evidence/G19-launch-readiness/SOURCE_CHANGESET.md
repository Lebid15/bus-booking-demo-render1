# G19 Source Changeset

Compared with the uploaded G18 RC1 package. Generated evidence files and build/cache artifacts are excluded from this source comparison.

- Added: **4**
- Modified: **23**
- Deleted: **0**

## Added files
- `apps/api/common/migrations/0002_widen_idempotency_scope.py`
- `apps/api/tests/test_audit_redaction.py`
- `docs/RELEASE_MANIFEST_G19.md`
- `scripts/check_python_dependencies.py`

## Modified files
- `.env.example`
- `README.md`
- `apps/api/Dockerfile`
- `apps/api/auditlog/services.py`
- `apps/api/common/models.py`
- `apps/api/config/settings.py`
- `apps/api/continuity/views.py`
- `apps/api/finance/migrations/0002_ledger_balance_trigger.py`
- `apps/api/notifications/services.py`
- `apps/api/payments/refund_services.py`
- `apps/api/requirements.txt`
- `apps/api/securityops/services.py`
- `apps/api/subscriptions/services.py`
- `apps/api/support/services.py`
- `apps/api/tests/test_e06_booking_confirmation.py`
- `apps/api/trips/reallocation_services.py`
- `apps/api/trips/services.py`
- `apps/web/Dockerfile`
- `apps/web/next.config.ts`
- `docker-compose.yml`
- `docs/FINAL_CLOSURE_STATUS.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `scripts/smoke_release.sh`

## Deleted files
- None

## Evidence bundle

- `docs/evidence/G19-launch-readiness/` contains PostgreSQL 18, Redis/Celery, API, frontend, backup/restore, PITR, load and quality-gate evidence.
