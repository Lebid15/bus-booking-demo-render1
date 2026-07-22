# تغيرات OpenAPI — Gate G3

الإصدار المنفذ: `4.0.0-e05`.

## المسارات العامة المكتملة

- `GET /v1/public/locations`
- `GET /v1/public/trips/search`
- `GET /v1/public/trips/{trip_id}`
- `GET /v1/public/trips/{trip_id}/seats`
- `POST /v1/public/trips/{trip_id}/seat-holds`
- `POST /v1/public/seat-holds/{hold_token}/release`

## ضوابط العقد

- البحث يتطلب `origin_id`, `destination_id`, و`date`، ويدعم `passengers` من 1 إلى 8.
- نتيجة الرحلة تعيد المكتب والناقل والنقطتين والوقت والسعر الصادق والتوفر وطرق الدفع وملخص الإلغاء ونسخة التسعير.
- إنشاء الـHold يتطلب `Idempotency-Key` وقائمة مقاعد وقائمة ركاب متساوية العدد.
- الخادم يرفض `PRICE_CHANGED`, `SEAT_NOT_AVAILABLE`, `SEAT_LAYOUT_MISMATCH`, و`TRIP_NOT_BOOKABLE` قبل أي تثبيت جزئي.
- رمز الـHold سر مؤقت؛ تمريره إلى `session_token` يجعل الخريطة تميز `held_by_you` دون كشف مالك أي Hold آخر.
- توليد OpenAPI والتحقق منه انتهيا بـ0 أخطاء. بقيت خمسة تحذيرات تسمية Enum تلقائية موروثة من تعدد حقول `status`.
