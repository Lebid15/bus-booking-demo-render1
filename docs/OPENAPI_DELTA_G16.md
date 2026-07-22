# OpenAPI Delta — G16 / E17

Baseline G15 generated contract: **115 paths / 138 operations**.

G16 generated contract: **125 paths / 149 operations**, validated with zero errors and zero warnings.

## Added operations

- `GET /v1/office/subscription`
- `GET /v1/office/subscription-plans`
- `POST /v1/office/subscription/change-request`
- `GET /v1/platform/subscription-plans`
- `POST /v1/platform/subscription-plans`
- `PATCH /v1/platform/subscription-plans/{plan_id}`
- `POST /v1/platform/offices/{office_id}/subscription`
- `GET /v1/platform/subscription-invoices`
- `POST /v1/platform/subscription-invoices/{invoice_id}/commands`
- `GET /v1/platform/subscription-change-requests`
- `POST /v1/platform/subscription-change-requests/{request_id}/commands`

## Contract behavior

- Office subscription responses expose the current snapshotted plan, period, status, usage and invoices.
- Plan creation and modification are platform-only and idempotent.
- Office plan changes are represented by an explicit reviewable request rather than an untracked direct mutation.
- Invoice commands support payment, void and uncollectible workflows while preserving ledger history.
- The public booking surface does not expose subscription billing data; it only receives the resulting commercial-availability decision.
