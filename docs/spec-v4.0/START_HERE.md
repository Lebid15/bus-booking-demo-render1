# ابدأ من هنا — الإصدار 4.0

## الحكم

الحزمة تغطي المنتج والهندسة والتشغيل والتصميم والسياسات والاختبار والإطلاق. يبدأ التطوير منها دون اختراع قواعد بديلة.

## ترتيب القراءة

1. `MASTER_PROJECT_SPECIFICATION_AR.md`
2. `00_GOVERNANCE/DOCUMENT_AUTHORITY_AND_PRECEDENCE.md`
3. `01_PRODUCT/END_TO_END_SERVICE_BLUEPRINT.md`
4. `02_BENCHMARK_OBILET/OBILET_PUBLIC_PRODUCT_AUDIT.md`
5. `03_UX_UI/INFORMATION_ARCHITECTURE.md` وكتالوجات الشاشات
6. `04_DOMAIN/DATABASE_SCHEMA_SPEC.md` و`postgresql_schema.sql`
7. `05_STATE_MACHINES/STATE_TRANSITION_CATALOG.md`
8. `07_PAYMENTS_FINANCE/LEDGER_EVENT_CATALOG.md`
9. `09_POLICIES_LEGAL/*`
10. `11_API/openapi.yaml` وكتالوج الأخطاء
11. `12_ARCHITECTURE/*`
12. `14_TESTING/*`
13. `15_DELIVERY/*`
14. `16_LAUNCH/*`

## قاعدة التنفيذ

كل مهمة ترتبط بـEpic ومعيار قبول وشاشة/Endpoint/كيانات متأثرة. لا يغلق العمل لأن الشاشة تبدو صحيحة؛ يجب إثبات قيود البيانات والحالات والمال والعزل والتدقيق.

## المسارات الآلية

`machine/` يحتوي جداول وشاشات وسياسات وأخطاء وآلات حالات وEpics بصيغ JSON/CSV لاستخدام أدوات البرمجة والتحقق.
