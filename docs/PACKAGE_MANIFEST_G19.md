# Package Manifest — v0.19.1 G19 RC2

## Package contents

- complete application source for API and Web;
- database migrations and seed commands;
- Docker and Docker Compose runtime definitions;
- product, implementation, closure and release documentation;
- G19 launch-readiness evidence, including PostgreSQL 18, Redis/Celery, Production runtime, load, backup/restore and PITR results;
- logical backup fixture used only for the isolated restore drill.

## Intentionally excluded

- Git metadata (not present in the uploaded source package);
- installed dependencies (`node_modules` and Python virtual environments);
- generated Next.js output (`.next`);
- Python/pytest/mypy/ruff caches and bytecode;
- local SQLite databases and TypeScript incremental caches;
- process IDs and Celery scheduler runtime databases.

## Release classification

**v0.19.1 RC2 / G19** — locally executable code and operational gates passed. External Staging, provider, security, legal/commercial and real-office pilot gates remain required before unconditional Production approval.
