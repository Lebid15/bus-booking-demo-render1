# اختبارات التزامن والمال

## التزامن

- 50 طلب Hold على مقعد واحد: لا أكثر من Hold فعال وفق القاعدة.
- تأكيدان متزامنان: Assignment نهائي واحد.
- انتهاء Hold بالتزامن مع إنشاء الحجز: نتيجة واحدة صحيحة لا حجز بلا مقعد.
- مسح QR مرتين: Boarding واحد.
- Webhook مكرر/خارج الترتيب: Payment/Ledger مرة واحدة.
- تغيير بولمان مع حجز جديد: قفل/منع التغيير وفق مرحلة الرحلة.

## المال

- كل Ledger event: مجموع Debit = مجموع Credit.
- Full/partial refund يعكس العمولة الصحيحة.
- Cash to office ينشئ Receivable للمنصة.
- Platform payment ينشئ Payable للمكتب بعد الخصومات.
- Chargeback مع Refund يمنع التعويض المزدوج.
- Settlement locked لا يعدل؛ Adjustment جديد فقط.
