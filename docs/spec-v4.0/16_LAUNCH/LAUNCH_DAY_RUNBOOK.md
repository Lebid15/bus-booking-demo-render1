# Runbook يوم الإطلاق

## الأدوار

Incident Commander، Technical Lead، Operations Lead، Support Lead، Finance/Reconciliation، Office Contact، Communications.

## قبل الفتح

- نسخة احتياطية واختبار صحة.
- تثبيت Build/Schema/Flags.
- Smoke search/hold/booking/payment/ticket.
- تأكيد الرحلات والمكاتب والموظفين.
- قنوات الدعم وWar Room.

## المراقبة

كل 15–30 دقيقة في الساعات الأولى: errors، latency، seat conflicts، payment mismatches، queue lag، support P1، office activity.

## Kill criteria

بيع مزدوج، خصم خاطئ واسع، تسرب Tenant، Manifest فاسد، عدم القدرة على صعود الركاب، أو فقد بيانات. عندها توقف الحجوزات الجديدة مع الحفاظ على القائمة والحجوزات القائمة.

## بعد اليوم

مصالحة كل العمليات، تقرير الحوادث، ملاحظات المكتب والزبائن، وقرار استمرار/تقييد.
