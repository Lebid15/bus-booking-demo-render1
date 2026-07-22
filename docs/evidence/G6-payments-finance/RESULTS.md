# Gate G6 / E07 — نتائج التنفيذ والتحقق

- التاريخ: 2026-07-21
- الفرع: `feature/e07-payments`
- التصنيف: Release Candidate
- المواصفة: `bus-booking-final-spec v4.0`

## نطاق التنفيذ

1. `PaymentIntent` لبدء الدفع المكتبي أو التحويل اليدوي أو الإلكتروني.
2. `PaymentTransaction` للحركة الفعلية مع منع تكرار أحداث المزود والمراجع.
3. رفع تحويل يدوي مع مرجع وبصمة إثبات ووقت تحويل فعلي وIdempotency.
4. قائمة مراجعة تحويلات المكتب، واعتماد أو رفض بسبب موثق وصلاحيات مالية.
5. تسجيل دفع نقدي بإيصال وAudit وقيد مالي واحد.
6. Webhook HMAC موقّع يُسجل أولًا في Inbox فريد مع بصمة للحمولة، ثم يُعالج بالخلفية بصورة Idempotent، ويحوّل اختلاف المبلغ/العملة إلى مصالحة.
7. مهمة Celery Beat لمعالجة Webhook Inbox كل 5 ثوانٍ مع حالات `received/processed/failed` دون إبقاء طلب المزود معلقًا على القيود والتذاكر.
8. إلغاء الحجوزات غير المدفوعة بعد المهلة وتحرير المقاعد بمهمة Celery Beat.
9. إعادة فحص المقاعد عند تحقق دفع وصل ضمن المهلة بعد تحرير الحجز.
10. عدم إعادة تأكيد الحجز عند بيع المقعد؛ فتح حالة استرداد أو بديل.
11. دليل حسابات وقيد مزدوج وDeferred Constraint Trigger خاص بـPostgreSQL.
12. Commission متوقعة من Snapshot الحجز بوصفها تأسيسًا لـE12.
13. واجهة العميل لإكمال الدفع والتحويل، وصفحة مكتب مالية تأسيسية.

## نتائج Backend

| الفحص | النتيجة |
|---|---|
| Django system check | PASS — 0 issues |
| Migration drift | PASS — no changes detected |
| هجرة قاعدة فارغة | PASS — جميع migrations، ومنها `payments.0001` و`finance.0001/0002` |
| Ruff | PASS |
| Mypy strict | PASS — 104 source files |
| Pytest | PASS — 66 collected؛ 63 passed، و3 PostgreSQL-only skipped محليًا |
| Bandit | PASS — لا نتائج متوسطة/عالية |
| OpenAPI validation | PASS — 0 errors، 0 warnings |

## نتائج Frontend

| الفحص | النتيجة |
|---|---|
| ESLint | PASS |
| TypeScript | PASS |
| Next.js production build | PASS — 14 route entries |
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

- `test_e07_ac01_office_cash_creates_one_transaction_balanced_ledger_receipt_and_audit`
- `test_e07_ac02_duplicate_transfer_reference_or_proof_is_rejected`
- `test_manual_transfer_submission_replay_is_idempotent_and_conflicting_reuse_is_rejected`
- `test_e07_ac03_transfer_before_deadline_verified_after_expiry_restores_available_seat`
- `test_e07_ac04_repeated_success_webhook_records_one_transaction`
- `test_webhook_signature_and_event_hash_are_tamper_evident`
- `test_e07_ac05_late_payment_after_seat_resold_does_not_reconfirm_and_opens_reconciliation`
- `test_e07_ac06_provider_amount_or_currency_mismatch_does_not_succeed_payment`
- `test_postgresql_rejects_unbalanced_ledger_entry_at_commit`

## الاختبارات المؤجلة محليًا

1. منافسة مستخدمين على Hold المقعد نفسه — PostgreSQL row locking/partial unique.
2. منافسة تأكيد حجزين على المقعد نفسه — PostgreSQL row locking.
3. رفض قيد مالي غير متوازن عند Commit — PostgreSQL deferred constraint trigger.

هذه الاختبارات ليست ملغاة؛ هي مدرجة في مجموعة Pytest وCI على PostgreSQL 18.

## فحص الاعتماديات

- `npm audit`: PASS — 0 vulnerabilities.
- `pip-audit`: لم يكتمل بسبب فشل DNS في حل `pypi.org` داخل بيئة التنفيذ.
- لا تسجل النتيجة كنجاح أو فشل أمني؛ يبقى `pip-audit` إلزاميًا في CI المتصل.

## قيود الإغلاق النهائي

1. نجاح الاختبارات الثلاثة الخاصة بـPostgreSQL 18 داخل CI.
2. نجاح `pip-audit` في بيئة متصلة بالإنترنت.
3. دورة الاسترداد والعكس المالي التفصيلية تتبع E09.
4. كسب العمولة والتسويات وحسابات المكاتب تغلق ضمن E12؛ المنفذ هنا تأسيس ضروري فقط.
5. تكامل مزود دفع حقيقي يحتاج مفاتيح وعقد Sandbox؛ المنفذ الحالي Adapter/Redirect وWebhook Inbox قابلان للاستبدال.
6. يحتفظ Inbox بحمولة مُطبّعة مقيدة الوصول وبصمة SHA-256؛ تشفير الحمولة الخام وسياسة الاحتفاظ الإنتاجية يغلقان ضمن موجة الأمان والتشغيل.
7. صفحة المكتب المالية الحالية تأسيسية؛ ربط الجداول الحية الشاملة والتقارير يتم مع توسعة لوحة المكتب والتسويات.

## حالة Git

- الفرع: `feature/e07-payments`
- Commit منطق الدفع والدفتر: `24d6727`
- Commit الواجهة والأدلة: رأس الفرع الموسوم `v0.7.0-g6-rc1`
- الوسم: `v0.7.0-g6-rc1`
- لم يتم الدمج إلى `main` قبل بوابة PostgreSQL 18 و`pip-audit` المتصل.

## القرار

يغطي G6 معايير E07 الستة محليًا ويؤسس سلامة الدفتر والعمولة دون ادعاء إغلاق E12. تبقى الحزمة Release Candidate حتى نجاح PostgreSQL CI و`pip-audit` المتصل.
