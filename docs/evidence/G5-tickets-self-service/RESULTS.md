# Gate G5 / E08 — نتائج التنفيذ والتحقق

- التاريخ: 2026-07-21
- الفرع: `feature/e08-tickets-self-service`
- التصنيف: Release Candidate
- المواصفة: `bus-booking-final-spec v4.0`

## نطاق التنفيذ

1. نموذج `tickets` مطابق لجوهر مخطط المصدر، مع إصدار وحالة وبصمة QR وتوقيع وتواريخ الإبطال/الاستخدام.
2. إصدار تذكرة مستقلة لكل راكب في الحجز المؤكد، وعدم إصدارها للحجز المنتظر للدفع.
3. QR opaque موقّع وقابل للإبطال، مع تحقق من HMAC وSHA-256 والحالة الحالية.
4. خدمة إعادة إصدار ذرية تبطل النسخة القديمة وتزيد `version_no`.
5. استرجاع الحجز كضيف بالـPNR ووسيلة الاتصال مع Rate limit وعدم كشف سبب الفشل.
6. عرض الحجز عبر Manage Token.
7. ربط حجز الضيف بحساب يملك وسيلة اتصال موثقة دون نسخ الحجز.
8. مستند مستقل لكل راكب يحتوي QR ويمكن طباعته أو حفظه PDF من المتصفح.
9. صفحة `/manage-booking` تعرض الحجز والركاب والتذاكر وQR.
10. Audit/Outbox موجودان في دورة الحجز، وأحداث `ticket.issued` و`ticket.revoked` و`ticket.reissued` تخرج من المعاملة.

## نتائج Backend

| الفحص | النتيجة |
|---|---|
| Django system check | PASS — 0 issues |
| Migration drift | PASS — no changes detected |
| Ruff | PASS |
| Mypy strict | PASS — 92 source files |
| Pytest | PASS — 55 passed، و2 PostgreSQL-only skipped محليًا |
| Bandit | PASS — لا نتائج متوسطة/عالية |
| هجرة قاعدة فارغة | PASS — جميع migrations، وتشمل `tickets.0001` |
| OpenAPI validation | PASS — 0 errors، 5 enum-name warnings موثقة |

## نتائج Frontend

| الفحص | النتيجة |
|---|---|
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 13 route entries |
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

- `test_e08_ac01_confirmed_guest_booking_issues_ticket_per_passenger`
- `test_e08_awaiting_payment_booking_does_not_issue_active_ticket`
- `test_e08_guest_manage_token_and_lookup_retrieve_ticket`
- `test_e08_ac02_lookup_is_generic_and_rate_limited`
- `test_e08_ac03_reissue_revokes_old_qr_and_increments_version`
- `test_e08_ac04_ticket_document_and_qr_are_available_without_email`
- `test_e08_ac05_verified_customer_links_guest_booking_without_copy`
- `test_e08_ticket_qr_is_tamper_evident_and_document_requires_manage_token`

## قيود الإغلاق النهائي

1. اختبارا التزامن السابقان لمخزون المقاعد وتأكيد الحجز ما زالا SKIP محليًا ويجب أن ينجحا على PostgreSQL 18 في CI.
2. SQLite لا تثبت القيود الجزئية أو `SELECT FOR UPDATE`؛ استخدمت فقط لبقية الاختبارات والهجرة النظيفة.
3. `pip-audit` تعذر بسبب فشل DNS نحو PyPI، والسجل محفوظ، ويبقى الفحص إلزاميًا في CI.
4. E08-AC03 مكتمل في خدمة الإبطال وإعادة الإصدار والتحقق، لكن ربطها بأوامر تعديل المقعد أو الراكب End-to-End سيتم عند تنفيذ E09.
5. استخدام QR مرة واحدة أثناء الصعود والتعامل مع مسحين متزامنين يتبع E10.
6. المستند الحالي HTML قابل للطباعة أو الحفظ PDF من المتصفح؛ توليد PDF خادمي مخصص يمكن إضافته لاحقًا دون تغيير عقد Ticket.

## القرار

يغلق G5 الوظائف الأساسية لـE08: إصدار التذكرة لكل راكب، QR الموقّع والقابل للإبطال، الاسترجاع الذاتي، مستند الطباعة، وربط الحجز بالحساب. تبقى الحزمة Release Candidate حتى نجاح PostgreSQL CI و`pip-audit` المتصل، وإكمال الربط End-to-End مع أوامر التعديل في E09.
