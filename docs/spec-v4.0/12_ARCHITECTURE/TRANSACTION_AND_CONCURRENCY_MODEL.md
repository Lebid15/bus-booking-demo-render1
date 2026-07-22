# المعاملات والتزامن

## إنشاء الحجز

داخل Transaction واحدة: قفل/تحقق Seat Hold، فحص المخطط والجنس، إنشاء booking/passengers/assignments/snapshots، إنشاء commission expected، وOutbox. Unique constraints هي خط الدفاع الأخير.

## الدفع

Provider event unique. المعالجة تحت قفل payment/booking، وتولد Ledger event مرة واحدة. إعادة الطلب تعيد النتيجة الأصلية.

## الصعود

قفل ticket/current issuance ثم إنشاء boarding event. مسحان متزامنان ينتجان نجاحًا واحدًا ونتيجة Already Used للأخرى.

## Optimistic locking

كيانات التحرير تستخدم `version` وIf-Match أو حقل version. التعارض لا يكتب فوق تغيير حديث.

## Jobs

كل Job قابل للتكرار ويستخدم cursor/claim وdedupe. انتهاء Holds لا يحرر assignment نهائيًا ولا ينفذ مرتين.
