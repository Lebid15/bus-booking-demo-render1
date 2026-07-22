# G14 / E14 Security, Privacy and Fraud — Quality Results

## Implemented

- Tenant-safe private upload intents whose ownership is derived from the authenticated user and office membership.
- Purpose-specific MIME, extension and size allowlists before any upload URL is issued.
- Quarantine-first file lifecycle with pluggable malware scanning and promotion to private storage only after a clean result.
- Generic `RESOURCE_NOT_FOUND` responses for cross-office file access without owner, count or sensitive metadata.
- Data-subject export requests and MFA-protected account deletion.
- Account disablement and anonymisation while preserving mandatory booking, commission and financial records.
- Legal Hold placement/release and an audited retention worker that skips protected subjects.
- Rule-based booking risk assessments with allow, step-up, manual-review and block decisions.
- One-time risk challenges and one-time step-up tokens; verified retries complete the original booking flow.
- Nested audit redaction for passwords, bearer/JWT values, tokens, OTP/MFA codes, PAN/CVV, private/API keys and sensitive free-text patterns.
- Deployment checks that reject mock upload storage, missing/non-importable scanners and the default development step-up code in production.
- User privacy console and platform security console for risk assessments and Legal Holds.
- CI/Makefile coverage for `securityops`, G14 OpenAPI validation and production deployment checks.

## Executed gates

- Specification package: PASS — 119 checksums, 68 tables, 103 acceptance criteria, 87 reference paths, 108 reference operations and 90 screens.
- Django system check: PASS.
- Production deploy check: PASS with zero warnings when explicit production contracts are supplied.
- Migration drift: PASS.
- Clean database migration: PASS, including `securityops.0001` and `securityops.0002`.
- Foundation permission seed: PASS.
- Full Backend suite: **115 passed, 4 skipped**.
- E14 focused suite: **8 passed**, including all six official acceptance criteria and two production configuration checks.
- The four skipped tests are inherited PostgreSQL-only concurrency/deferred-constraint gates.
- Ruff: PASS.
- Strict Mypy: PASS across **155 production files**.
- Bandit: PASS with no medium/high findings.
- OpenAPI: PASS — **108 paths, 131 operations, 0 errors, 0 warnings**.
- Frontend ESLint: PASS.
- TypeScript: PASS.
- Next.js production build: PASS — **34 routes**.
- npm audit: **0 vulnerabilities**.

## External/environment constraints

- `pip-audit` could not query PyPI because DNS resolution for `pypi.org` failed. The failure is environmental; the check remains mandatory in connected CI.
- PostgreSQL 18, Redis and separate Celery worker/beat processes are defined in Docker/CI but unavailable in the local execution environment. The four PostgreSQL-only tests are not claimed as passed.
- Production launch requires a real private object-storage endpoint and malware-scanner callable. The included local scanner is only a contract/test adapter.
- The current risk step-up delivery uses the configured development/Sandbox code contract. A real OTP delivery provider and production risk model remain launch gates.
- Retention periods and deletion/legal-hold procedures require final legal review before Production.
