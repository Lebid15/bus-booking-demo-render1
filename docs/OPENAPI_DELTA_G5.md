# تغيرات OpenAPI — Gate G5

الإصدار المنفذ: `4.0.0-e08`.

## المسارات الجديدة أو المكتملة

- `POST /v1/public/bookings/lookup`
- `GET /v1/public/bookings/{pnr}`
- `GET /v1/me/bookings`
- `POST /v1/me/bookings/link`
- `GET /v1/public/bookings/{pnr}/tickets/{ticket_id}/document`
- `GET /v1/public/tickets/{ticket_id}/qr.svg`

## توسعة استجابة Booking

كل راكب يعيد `ticket` أو `null`، ويشمل:

- `id`
- `version`
- `status`
- `qr_data` كحمولة opaque موقعة
- `seat_code`
- `pdf_url` لمسار المستند القابل للطباعة

## ضوابط الوصول

- Lookup يتطلب PNR ووسيلة الاتصال و`Idempotency-Key` ويطبق Rate limit.
- عرض الحجز والمستند وQR يتطلب Manage Token صالحًا.
- الخطأ في PNR أو وسيلة الاتصال يعيد الشكل نفسه `RESOURCE_NOT_FOUND`.
- QR لا يخزن كنص صريح، والرمز المعدل أو الإصدار المبطل يرفض.

## نتيجة التحقق

توليد OpenAPI والتحقق منه: 0 أخطاء. بقيت خمسة تحذيرات أسماء Enum غير مانعة وموروثة من تعدد حقول `status`.
