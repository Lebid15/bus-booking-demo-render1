# Gate G8 / E10 — نتائج التنفيذ والتحقق

- التاريخ: 2026-07-21
- الفرع: `feature/e10-boarding-offline`
- التصنيف: Release Candidate
- المواصفة: `bus-booking-final-spec v4.0`

## نطاق التنفيذ

1. دورة الصعود: وصول، تحقق، صعود، عكس، رفض، وNo-show لكل راكب.
2. QR أحادي الاستخدام مع قفل ذري للتذكرة والراكب والرحلة.
3. تحقق يدوي محكوم بسبب وAudit عند تعذر قراءة QR.
4. `BoardingEvent` Append-only وسجل Outbox لكل انتقال حساس.
5. Manifest إصداري حتمي مع SHA-256 عند إغلاق الصعود وعند المغادرة.
6. No-show آلي بعد الإغلاق وموعد الانطلاق، مع تجاوز حالات الرفض والمراجعة العاجلة.
7. حزمة Offline مشفرة وموقعة ومقيدة بجهاز موثوق وMFA ونسخة رحلة ووقت انتهاء.
8. مزامنة Offline Idempotent مع الاحتفاظ بالتعارضات وعدم إسقاطها بصمت.
9. موافقة منصة أحادية الاستخدام لعكس الصعود بعد المغادرة.
10. Idempotency مخزنة لأوامر الصعود وإنشاء الحزمة والمزامنة.
11. واجهة مكتب للمسح اليدوي/QR وManifest وإنشاء الحزمة ومزامنة الطابور.
12. إصلاح إعداد SQLite لاحترام `DATABASE_URL` وإثبات الهجرة من قاعدة جديدة فعلًا.

## نتائج Backend

| الفحص | النتيجة |
|---|---|
| Django system check | PASS — 0 issues |
| Migration drift | PASS — no changes detected |
| هجرة قاعدة فارغة | PASS — طُبقت جميع المهاجرات، ومنها `boarding.0001` |
| Ruff | PASS |
| Mypy strict | PASS — 114 source files |
| Pytest | PASS — 84 collected؛ 80 passed، و4 PostgreSQL-only skipped محليًا |
| اختبارات E10 | 11 collected؛ 10 passed، واختبار تزامن واحد مؤجل |
| Bandit | PASS — لا نتائج متوسطة/عالية |
| OpenAPI validation | PASS — 0 errors؛ 67 paths و80 operations |

## نتائج Frontend

| الفحص | النتيجة |
|---|---|
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 17 route entries |
| npm audit | PASS — 0 vulnerabilities |

## معايير القبول الجديدة

- `E10-AC01`: مسح QR متزامن يسجل صعودًا واحدًا — اختبار PostgreSQL موجود وإلزامي في CI.
- `E10-AC02`: تحقق يدوي مع سبب وAudit — PASS.
- `E10-AC03`: No-show يتجاوز الرفض والمراجعة العاجلة — PASS.
- `E10-AC04`: مزامنة Offline Idempotent مع تعارضات محفوظة — PASS.
- `E10-AC05`: تصحيح بعد المغادرة بموافقة منصة — PASS.
- `E10-AC06`: Manifest موقّع بالهاش وغير قابل للتعديل بصمت — PASS.
- Idempotency HTTP لأوامر الصعود والحزمة والمزامنة — PASS.
- QR أحادي الاستخدام وإبطال التكرار — PASS.

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

الاختبارات الأربعة موجودة في مجموعة Pytest وCI على PostgreSQL 18، ولا تعد ناجحة محليًا.

## فحص الاعتماديات

- `npm audit`: PASS — 0 vulnerabilities.
- `pip-audit`: تعذر بسبب فشل DNS في حل `pypi.org` داخل البيئة الحالية؛ لا تسجل النتيجة كنجاح أو اكتشاف ثغرة، ويبقى الفحص إلزاميًا في CI.

## قيود الإغلاق النهائي

1. نجاح اختبارات PostgreSQL 18 الأربعة داخل CI.
2. نجاح `pip-audit` في بيئة متصلة.
3. الاختبار الميداني الحقيقي لوضع Offline على جهاز بوابة وانقطاع شبكة فعلي يؤجل إلى Staging/التجربة التشغيلية.
4. الحزمة الحالية تسمح بإدخال طابور JSON واختبار البروتوكول؛ تخزين الطابور تلقائيًا داخل تطبيق/PWA جهاز مخصص يمكن تحسينه في موجة تجربة التشغيل دون تغيير العقد الخادمي.

## القرار

يغطي G8 معايير E10 ودورة الصعود وManifest والعمل دون اتصال محليًا. يبقى الإصدار Release Candidate حتى نجاح PostgreSQL CI و`pip-audit` المتصل.
