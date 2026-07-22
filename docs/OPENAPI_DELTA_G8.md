# تغيرات OpenAPI — Gate G8

الإصدار المنفذ: `4.0.0-g8-boarding-offline`.

## المسارات المكتملة

- `POST /v1/office/trips/{trip_id}/boarding`
- `GET /v1/office/trips/{trip_id}/manifest`
- `POST /v1/office/trips/{trip_id}/offline-package`
- `POST /v1/office/trips/{trip_id}/offline-sync`

## عقد تسجيل الصعود

- يتطلب سياق مكتب وصلاحية `office.boarding.scan`.
- يتطلب `Idempotency-Key` من 8 إلى 120 محرفًا.
- يقبل QR أو `passenger_id` للتحقق اليدوي.
- التحقق اليدوي للصعود يتطلب `reason_code`.
- الأوامر: `arrive` و`verify` و`board` و`reverse` و`deny` و`no_show`.
- QR المستخدم أو الإصدار المبطل لا يمكن إعادة استخدامه.
- عكس الصعود بعد المغادرة يتطلب `correction_approval_id` معتمدًا وغير مستخدم.

## عقد Manifest

- عدم تحديد `version` يعيد أحدث إصدار، ويمكن طلب إصدار محدد.
- الاستجابة تحمل رقم الإصدار والحالة وSHA-256 والحمولة الحتمية.
- يعاد حساب البصمة قبل الإرجاع؛ العبث يعيد `MANIFEST_INTEGRITY_FAILED`.

## عقد العمل دون اتصال

- إنشاء الحزمة يتطلب MFA حديثًا وجهازًا موثوقًا غير ملغى.
- الحزمة مشفرة بـFernet وموقعة بـHMAC ومقيدة بالجهاز ونسخة الرحلة ووقت الانتهاء.
- المزامنة تسمح فقط بـ`arrive` و`verify` و`board`.
- كل حدث يحمل `offline_event_id`، والتكرار لا ينشئ أثرًا ثانيًا.
- تعارض نسخة الرحلة أو الأمر غير المسموح أو حالة التذكرة يُحفظ كسجل قابل للمراجعة.
- الاستجابة تعيد أعداد المقبول والمكرر وقائمة التعارضات وتعليمة حذف الطابور المحلي.

## نتيجة التحقق

المخطط المولد يحتوي 67 مسارًا و80 عملية، ويُتحقق منه دون أخطاء في:

`docs/evidence/G8-boarding-offline/openapi-generated.yaml`
