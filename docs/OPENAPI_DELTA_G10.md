# تغيرات عقد OpenAPI — G10 / E12

أضيفت عمليات المال والتسويات التالية إلى العقد المولد:

- `GET /v1/office/settlements`
- `GET /v1/platform/settlements`
- `POST /v1/platform/settlements`
- `POST /v1/platform/settlements/{settlement_id}/commands`
- `GET /v1/platform/commission-profiles`
- `POST /v1/platform/commission-profiles`
- `PATCH /v1/platform/commission-profiles/{profile_id}`

## أوامر التسوية

يدعم مسار الأوامر:

- `calculate`
- `submit_review`
- `approve`
- `process`
- `mark_paid`
- `retry`
- `close`

جميع أوامر الكتابة الحساسة تتطلب `Idempotency-Key`، وتبقى هوية المكتب مشتقة من السياق الموثق ولا تُقبل من العميل لتحديد نطاق المكتب.

## نتيجة التحقق

- OpenAPI paths: 84.
- OpenAPI operations: 101.
- Validation errors: 0.
