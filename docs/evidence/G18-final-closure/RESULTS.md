# G17–G18 Final Closure Evidence

## Outcome

- E18 acceptance: **6/6 implemented and locally verified**.
- E19 acceptance: **5/5 implemented and verified, including a practical browser journey**.
- Full Backend suite: **133 passed, 4 PostgreSQL-only skipped**.
- Frontend production build: **40 routes**.
- OpenAPI: **132 paths / 157 operations**, 0 errors, 0 warnings.
- Functional project status: **19/19 epics, 103/103 acceptance criteria implemented**.

## Quality gates

| Gate | Result | Evidence |
|---|---|---|
| Fresh migration | PASS | `migrate-fresh.log` |
| Permission seed | PASS | `seed-foundation.log` |
| Notification-template seed | PASS — 120 templates | `seed-notifications.log` |
| Django check | PASS | `django-check.log` |
| Production deploy check | PASS | `django-deploy-check.log` |
| Migration drift | PASS | `migration-drift.log` |
| Pytest | 133 PASS / 4 PostgreSQL-only SKIP | `pytest.log`, `pytest.xml` |
| Ruff | PASS | `ruff.log` |
| Mypy strict | PASS — 174 source files | `mypy.log` |
| Bandit | PASS; informational parser warnings only | `bandit.log` |
| OpenAPI | PASS — 132 paths / 157 operations | `openapi-generated.yaml`, `openapi.log` |
| Specification validation | PASS | `spec-validation.log` |
| ESLint | PASS | `frontend-lint.log` |
| TypeScript | PASS | `frontend-typecheck.log` |
| UX static contract | 7/7 PASS | `ux-contract.log` |
| Next.js build | PASS — 40 routes | `frontend-build.log` |
| npm audit | 0 vulnerabilities | `npm-audit.log` |
| pip-audit | NOT RUN TO COMPLETION — PyPI DNS failure | `pip-audit.log` |

## Practical evidence

- Continuity cycle: `continuity-practical.log`.
- Running API requests: `practical-api.log`.
- Running Web output: `practical-web.log`.
- Browser result JSON: `ux-browser-results.json`.
- Booking success screenshot: `mobile-booking-success.png`.

## PostgreSQL-only gates still required

The local suite deliberately skips four checks whose correctness depends on PostgreSQL locking, partial constraints or deferred triggers:

1. concurrent seat hold has one winner;
2. concurrent booking confirmation has one winner;
3. deferred ledger-balance trigger rejects an unbalanced entry;
4. concurrent QR scans board once.

They remain mandatory in CI on PostgreSQL 18 before merging the final RC to `main`.
