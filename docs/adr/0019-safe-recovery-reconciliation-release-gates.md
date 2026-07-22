# ADR 0019 — Safe recovery, reconciliation and release gates

## Status

Accepted for the final functional Release Candidate.

## Context

The platform owns unique seat inventory and double-entry financial truth. During database failure or restoration it must never continue writes using Redis or stale application state. Reopening too early can sell the same seat twice or accept duplicated financial effects.

## Decision

1. PostgreSQL remains the only authoritative source for seats, payments and ledger entries.
2. A persisted platform continuity state controls `normal`, `maintenance`, `recovery` and `reconciliation` modes.
3. Non-operational writes return a retryable `503 PLATFORM_MAINTENANCE` outside normal mode.
4. Reopening requires a successful reconciliation run covering seat assignments, provider-payment identifiers and balanced ledger entries.
5. Recovery exercises calculate and retain RPO/RTO evidence; missing objectives are recorded as failure.
6. A failed Health or Smoke release result requires an explicit rollback reference before a release record can be accepted.
7. SEV-1 incidents require a commander, communications channel, timeline and postmortem.
8. Launch load evidence is rejected if it reports any duplicate seat or financial effect, regardless of latency success.

## Consequences

- Recovery is deliberately conservative and may delay sales while preserving financial and inventory correctness.
- Real PITR, failover and representative load evidence must still be produced in Staging/Production-like infrastructure.
- Operational state becomes visible through health checks and the platform continuity console.
