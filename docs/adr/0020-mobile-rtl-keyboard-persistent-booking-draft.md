# ADR 0020 — Mobile RTL, keyboard seats and persistent booking drafts

## Status

Accepted for the final functional Release Candidate.

## Context

The public flow must work in Arabic on ordinary phones and unreliable networks. Seat maps are visually dense, legal decisions must remain understandable, and a reload must not force customers to re-enter the booking without reason.

## Decision

1. Arabic is rendered with document-level RTL and locale-aware date, number and currency formatting.
2. Variable identifiers and amounts use bidirectional isolation where needed.
3. Seat buttons expose number, state, type and price to assistive technology.
4. Arrow keys plus Home/End navigate the seat grid; focus remains visible and unavailable seats remain inspectable.
5. Selected seats, passenger/contact data, hold state and idempotency keys are retained in session storage and cleared after release or successful confirmation.
6. Loading, empty and error boundaries include a clear next action.
7. Important policies are represented by localized, versioned summaries before confirmation with links to the complete text.
8. Mobile browser acceptance runs at 360×800 under slow-3G emulation and includes Axe, overflow, touch-target, persistence and complete-booking checks.

## Consequences

- The public booking flow can recover from ordinary reloads and weak connectivity without silently duplicating booking commands.
- Session storage is convenience state only; server-side holds, idempotency and inventory remain authoritative.
- Full visual review across the final brand and actual device matrix remains part of Staging acceptance.
