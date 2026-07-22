# ADR 0015 — Notification Outbox, Semantic Deduplication, Retry, and Escalation

## Status

Accepted for G13.

## Context

Booking, payment, trip-change, ticket, refund, office, and support transactions must not fail because an external communication provider is unavailable. Replaying an Outbox event must not create duplicate customer messages. Critical communication failures close to service time must become an operational task rather than disappear into logs.

## Decision

1. Domain transactions publish `OutboxEvent`; notification creation and external delivery run afterward.
2. `Notification` represents the semantic communication, while `NotificationDelivery` represents one channel attempt.
3. Deduplication uses SHA-256 over event meaning, aggregate, recipient, channel, and template version—not only the Outbox row ID.
4. Templates are immutable versions selected by effective time and recipient language, with Arabic fallback.
5. Destinations and Push tokens are encrypted; lookup/dedup uses hashes.
6. Retries use bounded exponential backoff and unique `(notification, channel, attempt_no)` attempts.
7. Exhausted critical delivery creates an alternative channel when possible and a P1 support escalation.
8. Material changes set `action_required`; notification delivery never changes a pending passenger decision into acceptance.
9. User preferences can disable optional channels but cannot rewrite immutable notification history.

## Consequences

- Domain success is isolated from provider failure.
- Operational teams can inspect and retry attempts without duplicating logical messages.
- Provider adapters remain replaceable; this release uses a deterministic mock adapter until external Sandbox credentials are provided.
- PostgreSQL/Redis/Celery integration remains a mandatory connected-environment gate.
