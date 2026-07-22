# Gate G3 / E05 — نتائج التنفيذ والتحقق

- التاريخ: 2026-07-21
- الفرع: `feature/e05-public-search-holds`
- التصنيف: Release Candidate
- المواصفة: `bus-booking-final-spec v4.0`

## نطاق التنفيذ

1. كتالوج مواقع عام بعقد مبسط ودعم البحث النصي والنوع.
2. بحث الرحلات حسب الأصل والوجهة والتاريخ وعدد الركاب مع المنطقة الزمنية للمكتب.
3. إخفاء الرحلات غير المفتوحة والمكاتب غير المسموح لها بحجوزات جديدة.
4. سعر معلن صادق يشمل الرسوم والخصومات المدونة في Snapshot.
5. تفاصيل الرحلة وخريطة المقاعد العامة وحالات التوفر.
6. Seat Hold جماعي آمن متعدد المقاعد مع Idempotency وRate limit.
7. إعادة تحقق خادمية وقفل للرحلة والمقاعد ومنع التثبيت المزدوج.
8. تحرير الـHold وانتهاؤه التلقائي عبر Celery Beat.
9. فهارس انتهاء الـHold واسترجاع المجموعة.
10. صفحات عامة فعلية للبحث والنتائج واختيار المقاعد وربط الركاب.

## نتائج Backend

| الفحص | النتيجة |
|---|---|
| Django system check | PASS — 0 issues |
| Migration drift | PASS — no changes detected |
| Ruff | PASS |
| Mypy strict | PASS — 86 source files |
| Pytest | PASS — 40 passed، و1 PostgreSQL-only skipped محليًا |
| Bandit | PASS — لا نتائج متوسطة/عالية |
| هجرة قاعدة فارغة | PASS — جميع migrations من الصفر |
| OpenAPI validation | PASS — 0 errors، 5 enum-name warnings موثقة |

## نتائج Frontend

| الفحص | النتيجة |
|---|---|
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 12 route entries |
| npm audit | PASS — 0 vulnerabilities |

## سلامة مواصفة المصدر

- Checksums verified: 119.
- Tables: 68.
- Acceptance criteria: 103.
- API paths: 87.
- API operations: 108.
- Screens: 90.
- النتيجة: PASS.

## الاختبارات الجديدة

- `test_e05_ac01_search_uses_office_local_date_and_only_bookable_trips`
- `test_e05_ac02_search_discloses_honest_price_fees_and_policy`
- `test_e05_ac05_restricted_office_trips_are_hidden`
- `test_public_hold_revalidates_inventory_and_is_idempotent`
- `test_idempotent_hold_replay_does_not_consume_rate_limit_twice`
- `test_e05_ac03_map_does_not_authorize_stale_seat_selection`
- `test_hold_release_and_expiry_restore_availability`
- `test_public_api_search_hold_and_release_contract`
- `test_e06_ac01_postgresql_concurrent_hold_has_single_winner`

## قيود الإغلاق النهائي

1. بيئة التنفيذ المحلية لا تحتوي PostgreSQL؛ اختبار التنافس المتوازي موجود ويعمل فقط عندما يكون `connection.vendor=postgresql`. يجب أن ينجح في CI على PostgreSQL 18 قبل الدمج إلى `main`.
2. SQLite استخدمت للفحص البنيوي والهجرة النظيفة والاختبارات غير المتوازية فقط، ولا تعد مصدر الحقيقة للقيود الجزئية أو `SELECT FOR UPDATE`.
3. `pip-audit` تعذر محليًا بسبب فشل DNS عند الوصول إلى PyPI. السجل محفوظ، والفحص يبقى إلزاميًا في CI.
4. هذه الحزمة تنشئ Hold وQuote فقط؛ إنشاء الحجز النهائي، Snapshot الركاب، قاعدة جنس المقاعد الكاملة، وPNR تتبع E06.

## القرار

معايير E05 الخمسة مغطاة، مع شريحة مبكرة من E06 لمنع السباق وانتهاء الـHold. الحزمة جاهزة كـ`G3 release candidate`، ولا يعلن الإغلاق النهائي أو الدمج إلى `main` قبل نجاح بوابة PostgreSQL 18 وRedis و`pip-audit` في CI.
