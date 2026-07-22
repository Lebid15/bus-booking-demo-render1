# مصفوفة ربط G10 — E12 العمولات والدفتر والتسويات

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E12-AC01 | كل `LedgerEntry` يتكون من Posting مدين ودائن، مع فحص خدمة وDeferred Constraint Trigger على PostgreSQL يمنع عدم التوازن عند نهاية المعاملة | `test_e12_ac01_unbalanced_ledger_entry_is_rejected` + `finance.0002` | PASS محليًا على فحص الخدمة؛ Trigger PostgreSQL إلزامي في CI |
| E12-AC02 | الدفع الإلكتروني قبل تقديم الخدمة يثبت في `CUSTOMER_FUNDS` ولا ينشئ إيراد عمولة؛ الاعتراف المالي يحدث عند إكمال الرحلة | `test_e12_ac02_electronic_capture_is_customer_funds_before_service` | PASS |
| E12-AC03 | الحجز المدفوع مباشرة في المكتب يولد ذمة عمولة على المكتب عند إكمال الرحلة | `test_e12_ac03_direct_payment_completion_creates_office_commission_receivable` | PASS |
| E12-AC04 | التسوية تجمع المستحقات الإلكترونية والعمولات المباشرة داخل العملة نفسها فقط، ولا تخلط العملات | `test_e12_ac04_settlement_nets_same_currency_only` | PASS |
| E12-AC05 | النزاع المفتوح يجمد مبلغ الحجز المتنازع عليه فقط، ويبقي بقية بنود التسوية قابلة للمعالجة | `test_e12_ac05_dispute_freezes_only_the_disputed_booking_amount` | PASS |
| E12-AC06 | تصحيح القيد المنشور ينشئ Reversal/Adjustment معاكسًا جديدًا، ويظل القيد الأصلي محفوظًا وغير محرر | `test_e12_ac06_reversal_creates_inverse_entry_without_editing_original` | PASS |
| E12-AC07 | منشئ التسوية لا يستطيع اعتمادها؛ الاعتماد يتطلب مستخدم منصة آخر وصلاحية وMFA حديثًا | `test_e12_ac07_creator_cannot_approve_own_settlement` | PASS |
| دورة التسوية | Draft → Calculated → Under review → Approved → Processing → Paid/Failed → Closed مع Idempotency وحراس حالة | `test_settlement_full_payment_cycle_posts_netting_and_payout_entries` | PASS |
| دفع التسوية | التحقق من حساب التحويل النشط، مرجع دفع فريد، وإنشاء قيود المقاصة والصرف المتوازنة | اختبار دورة الدفع الكاملة + Ledger assertions | PASS |
| حالة العمولة | Expected/Pending/Earned/In settlement/Paid/Reversed/Adjusted، وتحديث العمولة عند الاعتراف والتسوية | اختبارات AC02/AC03 ودورة الدفع | PASS |
| ملفات العمولة | ملفات إصدارية لا يُعاد تعديل تاريخها، مع MFA وIdempotency وAudit/Outbox عند الإنشاء والتحديث | API + migration `finance.0003` | PASS |
| صلاحيات المنصة | `platform.settlement.manage` و`platform.settlement.approve` و`platform.commission.manage` ضمن Seed الرسمي | `seed_foundation` على قاعدة نظيفة | PASS |
| واجهة المكتب | عرض التسويات والمبالغ المجمدة والصافية حسب العملة | `/office/settlements` + Frontend gates | PASS |
| واجهة المنصة | إنشاء وحساب ومراجعة واعتماد وتنفيذ التسويات، وإدارة ملفات العمولة | `/platform/finance` + Frontend gates | PASS |
| أمان النشر | CSRF وClickjacking middleware، HSTS/SSL redirect/cookies الآمنة حسب بيئة الإنتاج | `django-deploy-check.txt` | PASS |
