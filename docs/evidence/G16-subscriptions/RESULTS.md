# G16 / E17 — Subscriptions and Plans: Quality Results

## Scope delivered

- Versioned platform subscription plans.
- One-time office trial and paid subscription assignment.
- Snapshotted price, feature, limit and period truth.
- Office change requests with immediate or next-period application.
- Subscription invoices, payment recording, credit-note reversal and ledger integration.
- Progressive restriction of new commercial operations while preserving existing bookings and rights.
- Server-side branch, staff, vehicle and monthly-trip usage limits.
- Automated renewal, past-due, grace and expiry processing through Celery Beat.
- Office and platform subscription consoles.

## Automated results

- Full Backend suite: **125 passed, 4 PostgreSQL-only skipped**.
- Focused E17 suite: **5 passed**; all four official acceptance criteria passed plus the one-time-trial control.
- Django system check: **PASS**.
- Production deploy check: **PASS**.
- Empty-database migration: **PASS**, including `subscriptions.0001_initial`.
- Migration drift: **none**.
- Foundation permission seed: **PASS**.
- Ruff: **PASS**.
- Mypy strict: **PASS across 166 source files**.
- Bandit medium/high gate: **PASS**; parser-only comment warnings are retained in the evidence log.
- OpenAPI: **125 paths / 149 operations / 0 errors / 0 warnings**.
- Frontend lint and TypeScript: **PASS**.
- Next.js production build: **PASS, 39 routes**.
- npm audit: **0 vulnerabilities**.
- Specification v4.0 integrity: **PASS** — 119 checksums, 68 tables, 103 acceptance criteria, 87 source API paths, 108 source API operations and 90 screens.

## Deferred or external gates

1. Four existing concurrency/constraint tests remain intentionally PostgreSQL-only and must pass on PostgreSQL 18 CI:
   - concurrent seat hold;
   - concurrent booking confirmation;
   - deferred ledger-balance trigger;
   - concurrent QR scan.
2. `pip-audit` could not query PyPI because DNS resolution failed. The failure log is retained and the connected CI gate remains mandatory.
3. Production billing-provider/Sandbox credentials are not part of this source package.
4. Subscription pricing, tax treatment, trial length and final commercial limits require owner approval before production activation.

## Evidence files

- `pytest.log` and `pytest.xml`
- `migrate-clean.log`
- `migration-drift.log`
- `django-check.log`
- `deploy-check.log`
- `ruff.log`
- `mypy.log`
- `bandit.log` and `bandit.json`
- `openapi-generated.yaml`, `openapi.log` and `openapi-stats.log`
- `frontend-lint.log`, `frontend-typecheck.log`, `frontend-build.log`
- `npm-audit.log`
- `pip-audit.log`
- `spec-validation.log`
