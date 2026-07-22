# Evidence Bundle — G0 Foundation

- Spec checksum/stat validation: PASS.
- Django checks and migration drift check: PASS.
- Backend: 15 tests PASS.
- Ruff: PASS.
- Mypy strict: PASS.
- Bandit: PASS, no Medium/High findings.
- Frontend ESLint/TypeScript/Production build: PASS.
- npm audit: 0 vulnerabilities.
- Generated API schema: `openapi-generated.yaml`.
- Traceability: `../../TRACEABILITY_FOUNDATION.md`.

PostgreSQL service execution is delegated to CI because the current runner has no Docker daemon or local PostgreSQL binary.

- MFA challenge IP binding: PASS.
