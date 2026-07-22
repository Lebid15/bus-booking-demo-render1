# تغيرات OpenAPI — Gate G9

الإصدار المنفذ: `4.0.0-g9-reallocation-support`.

## تغيير البولمان وإعادة توزيع المقاعد

- `POST /v1/office/trips/{trip_id}/vehicle-change/preview`
- `POST /v1/office/trips/{trip_id}/vehicle-change/apply`
- `POST /v1/public/bookings/{pnr}/trip-changes/{change_id}/respond`

المحاكاة تتطلب رقم البولمان البديل ونسخة الرحلة، ولا تغيّر المخزون. الاستجابة تعيد خطة إصداريّة وخطًا لكل راكب مع المقعد السابق والمقترح والتعارض إن وجد. التطبيق لا يقبل خطة متعارضة أو قديمة، ويُغلق المخزون السابق ويُنشئ مخزونًا حاليًا جديدًا داخل معاملة واحدة.

رد المسافر محمي بـManage Token و`Idempotency-Key`، والخيارات هي: `accept` أو `alternative` أو `refund`.

## الدعم واستمرارية التشغيل

- `POST /v1/public/bookings/{pnr}/support-cases`
- `GET /v1/office/support-cases`
- `GET/POST /v1/office/support-cases/{case_id}/messages`
- `GET /v1/office/trips/{trip_id}/recovery-lookup`
- `GET /v1/platform/support-cases`
- `GET/POST /v1/platform/support-cases/{case_id}/messages`
- `POST /v1/platform/support-cases/{case_id}/commands`

الحالة العامة مرتبطة بحجز ورحلة ومكتب، وتحمل أولوية P0–P4 وموعد SLA. الردود والتغييرات الحساسة Idempotent. التحقق الاحتياطي يعيد حالة الحجز والراكب والتذكرة ويثبت `payment_required=false`.

## الرحلات المتوقفة

- أمر `interrupt` ضمن `POST /v1/office/trips/{trip_id}/commands`
- `POST /v1/platform/trips/{trip_id}/interruption/bookings`
- `POST /v1/platform/trips/{trip_id}/interruption/close`

الانقطاع ينشئ سجل معالجة لكل حجز متأثر. لا يسمح مسار الإغلاق بالانتقال إلى `completed` أو `cancelled` ما دام أي سجل بحالة `pending`.

## استجابة الحجز العام

أضيف `trip_changes` إلى استجابة الحجز العام، ويحتوي:

- `change_id`
- `change_type`
- `classification`
- `status`
- `response_deadline_at`
- `previous_snapshot`
- `new_snapshot`

كما تضاف `respond_trip_change` إلى `manage_actions` عند وجود رد معلق.

## نتيجة التحقق

المخطط المولد يحتوي 79 مسارًا و94 عملية، ويُتحقق منه دون أخطاء في:

`docs/evidence/G9-reallocation-support/openapi-generated.yaml`
