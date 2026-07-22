# المهام الخلفية والـOutbox

## أحداث Outbox

booking.created، payment.confirmed، ticket.issued، trip.changed، refund.requested، settlement.approved، notification.requested.

## قواعد

- يكتب Outbox في المعاملة نفسها.
- Dispatcher يطالب الصفوف بـSKIP LOCKED.
- لكل مستهلك dedupe key.
- فشل مزود خارجي لا يعيد Commit التجاري.
- Dead Letter Queue مع أدوات Replay وتدقيق.

## Jobs مجدولة

انتهاء Holds، انتهاء حجوزات غير مدفوعة، تنبيهات وثائق، فتح/إغلاق الصعود، تجميع التسويات، حذف البيانات، المصالحة، قياس SLA، والنسخ/اختبارات الصحة.
