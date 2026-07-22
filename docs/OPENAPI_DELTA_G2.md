# تغيرات OpenAPI — Gate G2

الإصدار المنفذ: `4.0.0-e04`.

## المسارات المضافة

- `GET /v1/office/trips`
- `POST /v1/office/trips`
- `GET /v1/office/trips/{trip_id}`
- `PATCH /v1/office/trips/{trip_id}`
- `POST /v1/office/trips/{trip_id}/commands`
- `GET /v1/office/trips/{trip_id}/seat-map`
- `GET /v1/platform/policies`
- `POST /v1/platform/policies`
- `GET /v1/public/policies/{policy_code}`

## أوامر الرحلة المغطاة

`schedule`, `publish`, `open_booking`, `open_boarding`, `close_boarding`, `depart`, `arrive`, `complete`, `cancel`.

## ضوابط العقد

- معرّف المكتب لا يقبل من العميل لاختيار النطاق.
- أوامر وتعديلات الرحلة تتطلب `version` للتزامن التفاؤلي.
- أخطاء المجال الأساسية مهيكلة، ومنها `TRIP_NOT_READY`, `TRIP_NOT_BOOKABLE`, `TRIP_DEPARTURE_BLOCKED`, و`TRIP_CANCEL_REASON_REQUIRED`.
- توليد المخطط والتحقق منه انتهيا بـ0 أخطاء. توجد خمسة تحذيرات تسمية Enum تلقائية ناتجة عن تعدد حقول `status`؛ لا تغيّر القيم أو صلاحية المخطط، وستعالج عند تثبيت أسماء Components النهائية دون إخفاء التحذيرات.
