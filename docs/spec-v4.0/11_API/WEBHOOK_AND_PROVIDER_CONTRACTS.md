# عقود Webhook والمزودين

## Webhook الدفع الوارد

1. التحقق من التوقيع والوقت.
2. تخزين payload خام مشفر/محمي وفق الاحتفاظ مع checksum.
3. dedupe على provider + event_id.
4. إرجاع 2xx بعد القبول للتجهيز، لا بعد كل الآثار الطويلة.
5. Job يعالج الحدث ويقفل payment/booking ويولد Ledger.
6. الأحداث خارج الترتيب تُقارن بحالة المزود ولا تخفض حالة نهائية دون قاعدة.

## Webhooks صادرة مستقبلًا

عند فتح API للشركاء: توقيع HMAC، retries، event version، delivery id، وإمكان replay. لا توجد في المرحلة الأولى كقناة عامة.

## Adapter Interface

`create_payment`, `query_payment`, `refund`, `verify_webhook`, `normalize_event`. لا تنتشر أنواع المزود داخل مجال الحجز.
