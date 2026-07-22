# OpenAPI Delta — G14 / E14

Baseline G13 generated contract: **100 paths / 122 operations**.

G14 generated contract: **108 paths / 131 operations**, validated with zero errors and zero warnings.

## Added operations

- `POST /v1/files/upload-intents`
- `POST /v1/files/{file_id}/complete`
- `POST /v1/me/data-export`
- `POST /v1/me/delete-account`
- `POST /v1/public/risk-challenges/{challenge_id}/verify`
- `GET /v1/platform/risk-assessments`
- `GET /v1/platform/legal-holds`
- `POST /v1/platform/legal-holds`
- `POST /v1/platform/legal-holds/{hold_id}/release`

## Contract characteristics

- Upload completion exposes only `file_id` and scan status; object keys and ownership metadata are never returned.
- Data-rights mutations require authentication and `Idempotency-Key`; account deletion additionally enforces recent MFA in the domain service.
- Risk challenge verification is public but challenge-bound, expiry-bound, attempt-limited and produces a one-time token.
- Platform risk and Legal Hold operations require platform permissions.
