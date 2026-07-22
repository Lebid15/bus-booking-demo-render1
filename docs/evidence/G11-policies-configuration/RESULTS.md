# Gate G11 / E13 — نتائج التنفيذ والتحقق

- التاريخ: 2026-07-21
- الفرع: `feature/e13-policies-configuration`
- التصنيف: Release Candidate
- المواصفة: `bus-booking-final-spec v4.0`

## نطاق التنفيذ

1. سجل إعدادات Typed ومركزي يحدد النطاق والقيمة الافتراضية والحدود والاختيارات وحالة Snapshot.
2. إعدادات مكتب إصداريّة لا تعدّل التاريخ السابق، وتُرفض خارج حدود المنصة بـ`CONFIGURATION_OUT_OF_RANGE`.
3. إعدادات منصة حساسة تمر بطلب ثم اعتماد مستخدم ثانٍ، مع MFA حديث وIdempotency.
4. إغلاق القيمة السابقة عند تاريخ نفاذ الإصدار الجديد دون حذفها.
5. سجل Audit كامل يشمل before/after والفاعل والسبب وتاريخ النفاذ.
6. إصدارات سياسات مستقبلية ببصمة SHA-256 وفترات نفاذ، دون أثر رجعي على الرحلات أو الحجوزات القائمة.
7. موافقات سياسة صريحة لكل حجز، مرتبطة بإصدار السياسة واللغة والكيان والوقت، مع تخزين hashes فقط لبيانات الشبكة والجهاز.
8. منع تأكيد الحجز إذا لم تُقبل جميع الإصدارات المطلوبة بـ`POLICY_ACCEPTANCE_REQUIRED`.
9. تثبيت إعدادات الرحلة المؤثرة داخل `pricing_snapshot.configuration` عند الجدولة.
10. واجهات تشغيل للمكتب والمنصة ومركز سياسات عام.

## نتائج Backend

| الفحص | النتيجة |
|---|---|
| Django system check | PASS — 0 issues |
| Django deploy check | PASS — 0 issues بإعدادات إنتاج |
| Migration drift | PASS — no changes detected |
| هجرة قاعدة فارغة | PASS — جميع المهاجرات ومنها `policies.0002` |
| Seed الصلاحيات | PASS — إضافة `office.configuration.manage` و`platform.configuration.manage` |
| Ruff | PASS |
| Mypy strict | PASS — 128 source files |
| Pytest | PASS — 103 collected؛ 99 passed، و4 PostgreSQL-only skipped محليًا |
| اختبارات E13 | PASS — 6/6 |
| Bandit | PASS — لا نتائج متوسطة/عالية |
| OpenAPI validation | PASS — 0 errors؛ 86 paths و105 operations |

## نتائج Frontend

| الفحص | النتيجة |
|---|---|
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 25 route entries |
| npm audit | PASS — 0 vulnerabilities |

## معايير القبول E13

- `E13-AC01`: قيمة مكتب خارج الحدود تُرفض بـ`CONFIGURATION_OUT_OF_RANGE` — PASS.
- `E13-AC02`: إصدار سياسة مستقبلي لا يغيّر Snapshot حجز قائم — PASS.
- `E13-AC03`: الحجز دون جميع الموافقات المطلوبة يُرفض بـ`POLICY_ACCEPTANCE_REQUIRED` — PASS.
- `E13-AC04`: الموافقة تحفظ الإصدار واللغة والوقت والكيان دون أسرار خام — PASS.
- `E13-AC05`: اعتماد التعديل الحساس يسجل before/after والفاعل والسبب وتاريخ النفاذ — PASS.
- Snapshot الإعدادات عند جدولة الرحلة يبقى ثابتًا بعد تغير الإعداد الحي — PASS إضافي.

## سلامة مواصفة المصدر

- Checksums verified: 119.
- Tables: 68.
- Acceptance criteria: 103.
- API paths: 87.
- API operations: 108.
- Screens: 90.
- النتيجة: PASS.

## الاختبارات المؤجلة محليًا

1. منافسة مستخدمين على Hold المقعد — PostgreSQL row locking/partial unique.
2. منافسة تأكيد حجزين — PostgreSQL row locking.
3. Trigger توازن Ledger المؤجل — PostgreSQL deferred constraint trigger.
4. مسح QR متزامن من بوابتين — PostgreSQL row locking.

هذه الاختبارات موجودة في Pytest وCI على PostgreSQL 18، ولا تعد ناجحة محليًا.

## فحص الاعتماديات

- `npm audit`: PASS — 0 vulnerabilities.
- `pip-audit`: تعذر بسبب فشل DNS في حل `pypi.org` داخل البيئة الحالية. النتيجة ليست نجاحًا ولا اكتشاف ثغرة، ويبقى الفحص إلزاميًا في CI؛ السجل محفوظ في `pip-audit.txt`.

## قيود الإغلاق النهائي

1. نجاح اختبارات PostgreSQL 18 الأربعة داخل CI.
2. نجاح `pip-audit` في بيئة متصلة.
3. مراجعة قانونية نهائية لنصوص السياسات قبل نشرها في Production.
4. اختبار موافقات اللغة والإصدار على Staging مع قنوات الواجهة الحقيقية.

## القرار

يغطي G11 معايير E13 محليًا: الإعدادات الإصداريّة، حدود المنصة، الاعتماد المزدوج، Versioning للسياسات، الموافقات الصريحة، وSnapshot الإعدادات. يبقى الإصدار Release Candidate حتى نجاح PostgreSQL CI و`pip-audit` المتصل والمراجعة القانونية/التشغيلية على Staging.
