# تغيرات عقد OpenAPI — G11 / E13

تم إغلاق عمليات السياسات والإعدادات التالية في العقد المولد:

- `GET /v1/office/configuration`
- `PATCH /v1/office/configuration`
- `GET /v1/platform/configuration`
- `PATCH /v1/platform/configuration`
- `GET /v1/platform/policies`
- `POST /v1/platform/policies`
- `GET /v1/public/policies/{policy_code}`

## أوامر إعدادات المنصة

يدعم `PATCH /v1/platform/configuration` نمطين:

- `action=propose`: ينشئ تغييرات معلقة بعد MFA ويتطلب `Idempotency-Key`.
- `action=approve`: يعتمد IDs محددة بواسطة مستخدم منصة ثانٍ بعد MFA ويتطلب `Idempotency-Key`.

## إعدادات المكتب

- التعديل محكوم بالـRegistry وحدود المنصة.
- النطاق مشتق من جلسة المستخدم وعضوية المكتب.
- لا يقبل العميل `office_id` لتحديد Tenant.
- كل تعديل يتطلب السبب وMFA و`Idempotency-Key`.

## السياسات

- إنشاء الإصدار يتطلب MFA و`Idempotency-Key`.
- الإصدار يحمل اللغة، وقت النفاذ، المحتوى، قواعد الآلة، وبصمة SHA-256.
- الاستعلام العام يدعم `office_id` و`language` بصورة اختيارية.

## نتيجة التحقق

- OpenAPI paths: 86.
- OpenAPI operations: 105.
- Validation errors: 0.
