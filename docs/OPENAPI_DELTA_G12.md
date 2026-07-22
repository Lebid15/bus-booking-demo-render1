# OpenAPI Delta G12

Added:

- `GET /v1/platform/offices/{office_id}`
- `POST /v1/platform/offices/{office_id}/status`
- `GET|POST /v1/platform/offices/{office_id}/violations`
- `POST /v1/platform/offices/{office_id}/violations/{violation_id}/commands`
- `GET /v1/platform/audit-logs`
- `GET /v1/platform/reports/summary`
- `GET /v1/office/reports/summary`

The existing `GET /v1/platform/offices` endpoint was extended with `q` and `status` filters rather than duplicated.
