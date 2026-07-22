# المراقبة وSLO

## مؤشرات تقنية

Latency وerror rate لكل Endpoint، DB locks، queue lag، webhook delay، notification delivery، file scan backlog، cache health.

## مؤشرات مجال

Seat conflicts، holds expired، bookings created/paid، payment mismatches، duplicate events، refund aging، denied boarding، office SLA.

## SLO أولية

- مسار البحث والحجز متاح 99.5% أثناء Pilot بعد استثناء صيانة معلنة.
- صفر فقد بيانات مقاعد/مال مقبول.
- معالجة Webhook ضمن دقائق في الحالة الطبيعية.
- P1 acknowledgment وفق سياسة الدعم.

لا تحتوي Metrics labels على PNR أو هاتف أو اسم.
