# تغيرات OpenAPI — Gate G6

الإصدار المنفذ: `4.0.0-g6-payments`.

## المسارات الجديدة أو المكتملة

- `POST /v1/public/bookings/{pnr}/payments`
- `POST /v1/public/payment-intents/{intent_id}/manual-transfer`
- `POST /v1/office/bookings/{booking_id}/payments/cash`
- `GET /v1/office/manual-payments`
- `POST /v1/office/manual-payments/{submission_id}/verify`
- `POST /v1/webhooks/payments/{provider_code}`

## توسعة استجابة Booking

أضيف إلى استجابة الحجز المدار:

- `payment_methods`: الطرق المثبتة في Snapshot الرحلة.
- `outstanding_amount`: المتبقي الفعلي بعد الحركات المسجلة.

## عقود الحماية

- كل أمر إنشاء أو تسجيل دفع تفاعلي يتطلب `Idempotency-Key`.
- بدء الدفع العام يتطلب Manage Token صالحًا للحجز.
- تسجيل النقد والتحقق من التحويل مقيدان بسياق المكتب والصلاحية الخادمية.
- Webhook يتطلب `X-Payment-Signature` صحيحًا ويطابق حمولة الطلب الخام.
- الطلب الصحيح يُسجل في Webhook Inbox ويرد للمزود مباشرة؛ المعالجة المالية تتم بخلفية Idempotent.
- إعادة `provider_event_id` بالحمولة نفسها آمنة، أما تغييره مع بصمة حمولة مختلفة فيُرفض.
- `provider_event_id` ومرجع التحويل وبصمة الإثبات فريدة.
- اختلاف مبلغ أو عملة المزود لا ينجح الدفع، بل يفتح حالة مصالحة.

## نماذج الاستجابة الأساسية

`PaymentIntent` يعيد:

- `id`
- `method_type`
- `status`
- `amount`
- `currency`
- `provider_action`
- `expires_at`

## نتيجة التحقق

تم توليد OpenAPI والتحقق منه بنجاح: **0 أخطاء و0 تحذيرات** بعد تثبيت أسماء الـEnums المتكررة صراحة.
