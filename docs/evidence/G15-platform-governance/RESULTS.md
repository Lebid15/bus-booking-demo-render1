# G15 / E16 Platform Governance — Quality Results

## Implemented

- Explicit platform role assignments and fine-grained permissions for support, finance, compliance and administrators.
- Production guard that rejects the temporary legacy administrator fallback.
- Dual approval for office suspension and termination with fresh MFA, independent approver and audited execution.
- Preservation of existing bookings and obligations while stopping future sales for suspended offices.
- Financial dispute workflow with office evidence, reasoned initial decision, one appeal and independent final review.
- Permission-separated financial effects posted through balanced ledger entries, including reversal on appeal.
- Platform and office financial reports derived from `LedgerPosting`, grouped and reconciled by currency.
- Platform approval, platform dispute and office dispute operational consoles.
- CI and generated OpenAPI coverage updated for G15.

## Executed gates

- Specification package: PASS — 119 checksums, 68 tables, 103 acceptance criteria, 87 reference paths, 108 reference operations and 90 screens.
- Django system check: PASS.
- Production deploy check: PASS with explicit platform roles required and the legacy fallback disabled.
- Migration drift: PASS.
- Clean database migration: PASS, including `identity.0003`, `adminops.0002` and `finance.0004`.
- Foundation permission/role seed: PASS.
- Notification template seed: PASS — 120 templates.
- Full Backend suite: **120 passed, 4 skipped**.
- E16 focused suite: **5 passed**, covering all five official acceptance criteria.
- The four skipped tests are inherited PostgreSQL-only row-lock/deferred-constraint gates.
- Ruff: PASS.
- Strict Mypy: PASS across **158 production files**.
- Bandit: PASS with no unresolved findings.
- OpenAPI: PASS — **115 paths, 138 operations, 0 errors, 0 warnings**.
- Frontend ESLint: PASS.
- TypeScript: PASS.
- Next.js production build: PASS — **37 routes**.
- npm audit: **0 vulnerabilities**.

## External/environment constraints

- `pip-audit` could not query PyPI because DNS resolution for `pypi.org` failed. The failure is environmental and remains a mandatory connected-CI gate.
- PostgreSQL 18 and Redis are defined in Docker/CI but unavailable in the local execution environment. The four PostgreSQL-only tests are not claimed as passed.
- Production rollout requires migration of every platform staff account to an explicit role assignment before `PLATFORM_RBAC_LEGACY_ADMIN_FALLBACK=false` is enforced.
- A staging exercise must verify support-only, finance-only and approval-only accounts with real session MFA evidence.
