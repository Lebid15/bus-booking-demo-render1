# مسار التطوير والإصدار

## الفروع

- `main`: محمي ولا يُدفع إليه مباشرة.
- `feat/<epic>-<slice>`: حزمة عمل مترابطة.
- `fix/<epic>-<issue>`: إصلاح محدد.

## بوابة كل حزمة

1. ربط Epic ومعايير القبول في وصف العمل.
2. Migration + domain service + API/UI عند الحاجة.
3. اختبارات Unit/Integration/Security المناسبة.
4. `ruff` و`mypy` وDjango checks وOpenAPI generation.
5. PostgreSQL integration للحجز والمال والتزامن.
6. Evidence Bundle وتحديث مصفوفة الربط.
7. Squash merge بعد نجاح CI.

## التزامات المراجعة

- لا يُخفف قيد قاعدة بيانات لإمرار واجهة.
- لا تضاف قيمة تجارية كثابت في Frontend.
- لا يُقبل `office_id` لتحديد Tenant في عمليات المكتب.
- لا تُدمج عملية مالية أو مقعد دون Idempotency/atomicity/audit المناسب.
