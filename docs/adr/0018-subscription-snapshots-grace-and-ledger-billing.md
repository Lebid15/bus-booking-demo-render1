# ADR 0018 — Subscription snapshots, grace enforcement and ledger billing

## Status

Accepted for G16 Release Candidate.

## Context

Office subscriptions are independent from booking-channel commissions. A plan can change over time, but a paid subscription period must retain the price, features and limits that were accepted for that period. Expiry must stop new commercial activity without deleting or blocking access to existing bookings, tickets, refunds, disputes or financial obligations. Subscription invoices also need to reconcile with the existing double-entry ledger.

## Decision

### Versioned commercial truth

1. `SubscriptionPlan` stores the platform plan version and its effective window.
2. `OfficeSubscription` stores immutable price, feature and limit snapshots for its billing period.
3. Updating a plan affects only later assignments or renewals; historical periods are never recalculated from the live plan.
4. Only one trial/active/past-due/grace subscription may exist for an office at a time.
5. Trial history is permanent enough to prevent a second trial even after the first period ends.

### Progressive enforcement

1. `trial`, `active` and `past_due` allow new commercial operations.
2. `grace`, `suspended`, `cancelled` and `expired` are read-only for new commercial operations.
3. Existing bookings and customer rights remain accessible and operable.
4. Branch, staff, vehicle and monthly-trip limits are checked in domain services before creation.
5. During rollout, enforcement remains dormant until an active plan catalogue exists; once plans exist, missing subscriptions fail closed.

### Billing and renewal

1. Subscription assignment creates an invoice and a balanced `SUBSCRIPTION_INVOICED` ledger entry.
2. Marking the invoice paid creates a balanced `SUBSCRIPTION_PAID` entry with a unique payment reference.
3. Voiding or declaring an invoice uncollectible creates an explicit reversal/credit-note entry; posted ledger history is not edited.
4. The periodic Celery task renews eligible subscriptions, creates the next period from the current plan version, and progresses overdue subscriptions through grace to expiry.
5. Idempotency protects plan changes, assignments, invoice commands and change-request decisions.

## Consequences

- Plan and price history remain auditable and cannot be rewritten by later catalogue changes.
- Expired offices retain operational access to existing customer obligations while losing new-sale capability.
- Usage-limit checks now exist in several domain services and must remain part of regression testing.
- Actual external collection providers remain an adapter concern; this release records and reconciles billing internally.
