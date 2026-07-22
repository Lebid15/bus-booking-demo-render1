SHELL := /bin/bash

.PHONY: bootstrap up down logs backend-test backend-check frontend-check validate-spec check

bootstrap:
	cp -n .env.example .env || true
	docker compose build
	docker compose run --rm api python manage.py migrate
	docker compose run --rm api python manage.py seed_foundation
	docker compose run --rm api python manage.py seed_notification_templates

up:
	docker compose up --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

backend-test:
	cd apps/api && pytest

backend-check:
	cd apps/api && ruff check . && mypy common identity organizations geography fleet policies trips bookings tickets payments finance auditlog boarding support adminops notifications securityops subscriptions continuity config && python manage.py check && python manage.py makemigrations --check --dry-run && bandit -q -r . -x './tests,./*/migrations'

frontend-check:
	cd apps/web && npm run lint && npm run typecheck && npm run test:ux-contract && npm run build && npm audit --audit-level=moderate

validate-spec:
	python scripts/validate_spec_package.py

check: validate-spec backend-check backend-test frontend-check
