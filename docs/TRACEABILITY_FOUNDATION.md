# مصفوفة ربط حزمة الأساس

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E01-AC01 | تطبيع البريد والهاتف، قيد فريد، حساب غير مفعل، تحدي تحقق، تفعيل ذري بعد الرمز | `test_e01_ac01_registration_normalizes_phone_and_prevents_duplicates` | PASS |
| E01-AC02 | منع إنشاء جلسة كاملة للأدوار الحساسة قبل TOTP | `test_e01_ac02_sensitive_office_user_must_complete_mfa` | PASS |
| MFA hardening | ربط تحدي MFA بعنوان الاتصال ومنع إعادة استخدامه من عنوان آخر | `test_mfa_challenge_is_bound_to_request_ip` | PASS |
| E01-AC03 | Access Token مرتبط بجلسة خادمية وفحص الإلغاء بكل طلب | `test_e01_ac03_revoked_session_is_rejected_immediately` | PASS |
| E01-AC04 | Rate limit تدريجي حسب المعرّف والشبكة برسالة لا تكشف الحساب | `test_e01_ac04_progressive_rate_limit_is_generic` | PASS |
| E01-AC05 | قائمة الجلسات وإلغاء جلسة محددة مع Audit | `test_e01_ac05_revoking_one_session_keeps_other_active_and_audits` | PASS |
| Tenant isolation | سياق المكتب مشتق من العضوية ولا يستخدم `office_id` الوارد | `test_office_context_is_derived_from_membership_not_request_office_id` | PASS |
| Fail closed | تعدد العضويات دون سياق محدد يرفض بدل اختيار مكتب خفيًا | `test_ambiguous_membership_context_fails_closed` | PASS |
| Audit logging | سجل Append-only مع حجب الأسرار وRequest ID | اختبارات MFA وإلغاء الجلسة | PASS |
| Observability baseline | Request ID وLiveness وReadiness | `test_platform_baseline.py` | PASS |
| Outbox / Idempotency skeleton | نماذج ومهاجرات معيارية أولية | migration check | PASS |
