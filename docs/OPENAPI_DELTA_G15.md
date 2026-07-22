# OpenAPI Delta — G15 / E16

Baseline G14 generated contract: **108 paths / 131 operations**.

G15 generated contract: **115 paths / 138 operations**, validated with zero errors and zero warnings.

## Added operations

- `GET /v1/platform/approvals`
- `POST /v1/platform/approvals/{approval_id}/commands`
- `GET /v1/platform/disputes`
- `POST /v1/platform/disputes/{dispute_id}/commands`
- `GET /v1/office/disputes`
- `POST /v1/office/disputes/{dispute_id}/respond`
- `POST /v1/office/disputes/{dispute_id}/appeal`

## Changed behavior

- Critical office status changes return a pending approval instead of mutating the office immediately.
- Platform endpoints enforce the permission declared by each view, not only the broad `is_platform_staff` flag.
- Platform and office financial summaries are sourced from ledger postings and expose debit, credit, posting count and balance status by currency.
- Dispute decisions expose the reason, decision code, financial effect, appeal deadline and final appeal decision.
