# تغيرات OpenAPI — Gate G7

الإصدار المنفذ: `4.0.0-g7-changes-refunds`.

## المسارات المكتملة

- `GET /v1/public/bookings/{pnr}/cancellation-quote`
- `POST /v1/public/bookings/{pnr}/cancel`
- `POST /v1/office/bookings/{booking_id}/commands`
- `GET /v1/office/refunds`
- `POST /v1/office/refunds/{refund_id}/commands`
- `GET /v1/platform/refunds`
- `GET /v1/platform/chargebacks`

## عقد الإلغاء العام

- يتطلب Manage Token صالحًا.
- يمكن تحديد راكب أو أكثر عبر `passenger_id` المتكرر؛ عدم تحديده يعني جميع الركاب النشطين.
- Quote يحمل المبالغ والركاب والمهلة ورمزًا موقّعًا.
- التنفيذ يتطلب `Idempotency-Key` و`quote_token`.
- الاستجابة هي `Booking` المحدثة وفق عقد المصدر الرسمي، وليست غلافًا خاصًا.
- Quote قديم أو محرّف أو صادر لنسخة حجز سابقة يُرفض.

## أوامر المكتب

`POST /v1/office/bookings/{booking_id}/commands` يدعم:

- `replace_passenger`
- `change_seat`

ويفرض سياق المكتب وصلاحية `office.booking.manage` وIdempotency، ولا يقبل `office_id` من العميل.

## دورة الاسترداد

الأوامر المدعومة:

- `review`
- `approve`
- `reject`
- `process`
- `succeed`
- `fail`
- `retry`
- `cancel`

الحراس الأساسية:

- `DUAL_APPROVAL_REQUIRED`
- `CHARGEBACK_OPEN`
- `REFUND_AMOUNT_EXCEEDS_AVAILABLE`
- `REFUND_STATE_CONFLICT`
- MFA حديث فوق الحد المالي.

## نتيجة التحقق

يُولد المخطط ويُتحقق منه ضمن البوابة المحلية وCI في:

`docs/evidence/G7-changes-refunds/openapi-generated.yaml`
