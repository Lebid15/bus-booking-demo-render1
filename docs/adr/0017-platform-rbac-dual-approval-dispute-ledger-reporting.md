# ADR 0017 — Platform RBAC, dual approval, dispute decisions and ledger-backed reporting

## Status

Accepted for G15 Release Candidate.

## Context

Platform staff do not all have the same authority. Support personnel need operational access without settlement authority, critical office suspension must not be a single-actor action, and dispute decisions must be reviewable, financially consistent and appealable. Financial dashboards must also reconcile to the double-entry ledger rather than a separate collection of UI-oriented aggregates.

## Decision

### Platform roles

1. Platform access is granted through explicit `PlatformRoleAssignment` rows linked to versioned roles and permissions.
2. Each platform view declares a required permission; the permission layer enforces it before domain execution.
3. Support, finance, compliance and administrator roles are seeded separately.
4. A temporary legacy fallback remains available only for migration/development. Production deployment fails when it is enabled.

### Critical platform actions

1. Office suspension and termination create a pending `PlatformActionApproval`.
2. The requester must have fresh MFA evidence.
3. A second platform actor with approval permission must approve or reject the action.
4. The requester cannot approve their own request.
5. Execution changes only future sale eligibility; existing bookings, tickets, refunds and settlement obligations remain intact.

### Disputes

1. The dispute state machine supports office response, initial decision, one appeal, independent appeal decision and closure.
2. Every decision records a code, reasoning, financial effect and appeal deadline.
3. A financial effect requires `platform.dispute.finance` in addition to dispute-management permission.
4. Financial effects are posted as balanced ledger entries. An appeal reverses the initial entry before posting the final effect.
5. The initial decision maker cannot decide the appeal.

### Reporting

Platform and office finance summaries query `LedgerPosting` directly, group by currency and expose debit/credit equality. Payment-table or UI aggregates are not treated as the financial source of truth.

## Consequences

- Platform staff provisioning now requires explicit role assignment before production fallback can be disabled.
- Sensitive actions add a deliberate second-review step and require MFA evidence.
- Dispute appeal decisions can produce reversal entries, increasing ledger volume while preserving history.
- Financial reports remain reconcilable even when payment or booking projections are delayed.
