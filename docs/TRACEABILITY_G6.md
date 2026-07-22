# مصفوفة ربط G6 — E07 الدفع النقدي والتحويل والإلكتروني

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E07-AC01 | تسجيل قبض المكتب من مستخدم مخول مع `Idempotency-Key`، حركة دفع واحدة، إيصال، Audit، وقيد مزدوج متوازن | `test_e07_ac01_office_cash_creates_one_transaction_balanced_ledger_receipt_and_audit` | PASS محليًا؛ Trigger DB يعاد التحقق منه على PostgreSQL |
| E07-AC02 | فريدة مرجع التحويل وبصمة إثباته، ورفض أي إعادة استخدام عبر حجوزات مختلفة | `test_e07_ac02_duplicate_transfer_reference_or_proof_is_rejected` | PASS |
| Idempotency رفع التحويل | إعادة الطلب نفسه بالمفتاح نفسه تعيد النتيجة دون سجل جديد، وتغيير الحمولة بالمفتاح نفسه يرفض | `test_manual_transfer_submission_replay_is_idempotent_and_conflicting_reuse_is_rejected` | PASS |
| E07-AC03 | اعتماد `transferred_at` الحقيقي؛ بعد انتهاء المهلة يعاد فحص المخزون قبل إعادة الحجز وإصدار التذاكر | `test_e07_ac03_transfer_before_deadline_verified_after_expiry_restores_available_seat` | PASS |
| E07-AC04 | Webhook موقّع يُقبل في Inbox فريد ثم يعالج بالخلفية؛ إعادة الحدث لا تكرر Inbox أو الحركة أو القيد | `test_e07_ac04_repeated_success_webhook_records_one_transaction` | PASS |
| E07-AC05 | دفع متأخر بعد بيع المقعد يسجل المال ولا يعيد تأكيد الحجز، ويفتح مصالحة استرداد/بديل | `test_e07_ac05_late_payment_after_seat_resold_does_not_reconfirm_and_opens_reconciliation` | PASS |
| E07-AC06 | اختلاف المبلغ أو العملة ينشئ حركة Failed قابلة لمنع التكرار، ويبقي الحجز غير مدفوع ويفتح مصالحة | `test_e07_ac06_provider_amount_or_currency_mismatch_does_not_succeed_payment` | PASS |
| توازن الدفتر | تحقق تطبيقي قبل الإدخال وDeferred Constraint Trigger على `ledger_postings` عند commit | `assert_entry_balanced` و`test_postgresql_rejects_unbalanced_ledger_entry_at_commit` | CORE PASS؛ اختبار Trigger مؤجل إلى PostgreSQL CI |
| انتهاء مهلة الدفع | مهمة Celery دورية تلغي الحجوزات غير المدفوعة وتحرر الإسنادات وتصدر Outbox event | `expire_due_unpaid_bookings` واختبار AC03/AC05 | PASS |
| عمولة Snapshot | إنشاء Commission متوقعة من `booking.commission_snapshot` عند إنشاء الحجز دون الرجوع لإعداد حي لاحق | اختبار AC01 و`create_expected_commission` | PASS تأسيسي لـE12 |
| API العام | بدء نية دفع ورفع تحويل يدوي | OpenAPI generated + اختبارات الخدمة | PASS |
| API المكتب | تسجيل النقد، قائمة مراجعة التحويلات، واعتماد/رفض التحويل | OpenAPI generated + AC01/AC03 | PASS |
| Webhook المزود | تحقق HMAC قبل التسجيل، بصمة تمنع تغيير حمولة الحدث نفسه، Inbox بحالات معالجة، ومهمة Celery خلفية مع مصالحة للاختلافات | AC04/AC06 و`test_webhook_signature_and_event_hash_are_tamper_evident` | PASS |
| واجهة العميل | إدارة الحجز تعرض المبلغ المتبقي وطرق الدفع، بدء النية، رفع بيانات التحويل، ورابط المزود | ESLint + TypeScript + Next.js build | PASS |
| شاشة المكتب | `/office/payments` تعرض ضوابط ومسارات تشغيل المالية؛ البيانات الحية محمية بواجهات المكتب | Next.js build + API permissions | PASS تأسيسي |
