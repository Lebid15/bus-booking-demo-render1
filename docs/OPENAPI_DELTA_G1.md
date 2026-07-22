# OpenAPI Delta — G1

المخطط التنفيذي المولد من Django/DRF هو الدليل الحالي. الإضافات التالية مطلوبة لإغلاق E02/E03 ولم تكن كلها معرفة بتفصيل كافٍ في عقد v4.0 الأصلي:

## المكتب

- `GET|POST /v1/office/branches`
- `PATCH /v1/office/branches/{branch_id}`
- `GET|POST /v1/office/staff`
- `PATCH /v1/office/staff/{membership_id}`
- `GET /v1/office/verification`
- `POST /v1/office/verification/commands`
- `GET|POST /v1/office/verification/documents`
- `GET|POST /v1/office/payout-accounts`
- `POST /v1/office/payout-accounts/{account_id}/approve`
- `GET|POST /v1/office/seat-layouts`
- `POST /v1/office/seat-layouts/{layout_id}/versions`
- `GET|POST /v1/office/vehicles`
- `PATCH /v1/office/vehicles/{vehicle_id}`
- `GET|POST /v1/office/drivers`
- `PATCH /v1/office/drivers/{driver_id}`

## المنصة والعام

- `GET /v1/public/locations`
- `GET|POST /v1/platform/locations`
- `PATCH /v1/platform/locations/{location_id}`
- `GET|POST /v1/platform/routes`
- `PATCH /v1/platform/routes/{route_id}`
- `GET /v1/platform/offices`
- `POST /v1/platform/offices/{office_id}/verification/commands`
- `PATCH /v1/platform/offices/{office_id}/documents/{document_id}`

جميع أوامر الكتابة الحساسة تتطلب `Idempotency-Key`. تغيير حساب التسوية يتطلب كذلك MFA حديثًا واعتمادًا ثانيًا.
