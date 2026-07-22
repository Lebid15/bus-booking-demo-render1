# مصفوفة ربط G11 — E13 السياسات والإعدادات والموافقات

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E13-AC01 | Registry Typed يحدد bounds لكل مفتاح؛ تعديل المكتب يمر عبر `validate_value` ولا ينشأ أي إصدار عند الرفض | `test_e13_ac01_office_configuration_outside_platform_bounds_is_rejected` | PASS |
| E13-AC02 | كل سياسة إصدار مستقل بوقت نفاذ وبصمة؛ الحجز يحتفظ `policy_snapshot` و`terms_version_ids` المجمدين | `test_e13_ac02_future_policy_does_not_change_existing_booking_snapshot` | PASS |
| E13-AC03 | `create_public_booking` يقارن الإصدارات المقبولة بالإصدارات المطلوبة للرحلة قبل استهلاك الـHold | `test_e13_ac03_missing_required_policy_acceptance_blocks_confirmation` | PASS |
| E13-AC04 | `PolicyAcceptance` يحفظ policy_version، subject booking، accepted_at، اللغة عبر الإصدار، وIP/User-Agent hashes فقط | `test_e13_ac04_acceptance_records_version_language_time_and_booking_without_raw_secrets` | PASS |
| E13-AC05 | تغيير منصة حساس = proposal ثم approver ثانٍ؛ Audit يحتوي before/after/reason/effective_from والفاعلين | `test_e13_ac05_sensitive_platform_change_requires_second_approver_and_audits_before_after_reason` | PASS |
| Snapshot الإعدادات | مفاتيح الإعدادات ذات `snapshot=True` تثبت في `Trip.pricing_snapshot.configuration` عند الجدولة | `test_e13_configuration_snapshot_is_frozen_when_trip_is_scheduled` | PASS |
| تاريخ الإعدادات | `ConfigurationValue` صفوف إصداريّة مع effective_from/effective_to؛ القيمة السابقة تغلق ولا تحذف | migration `policies.0002` + services | PASS |
| اعتماد المنصة | يمنع المنشئ من اعتماد تغييره، ويتطلب MFA حديثًا وIdempotency | اختبار AC05 | PASS |
| إعدادات المكتب | هوية المكتب مشتقة من `OfficeContext` ولا يقبل `office_id` من Body لتحديد النطاق | `OfficeConfigurationView` + `HasOfficeContext` | PASS |
| سياسات عامة | عرض الإصدار النافذ حسب الكود والمكتب واللغة، مع fallback لسياسة المنصة | `/v1/public/policies/{policy_code}` | PASS |
| صلاحيات | `office.configuration.manage` و`platform.configuration.manage` ضمن Seed الرسمي | `seed_foundation` على قاعدة نظيفة | PASS |
| واجهات المكتب | تعديل الإعدادات وعرض القيم والحدود والمصدر | `/office/settings` | PASS |
| واجهات المنصة | اقتراح التغيير واعتماد مستخدم ثانٍ وعرض pending/effective | `/platform/settings` | PASS |
| مركز السياسات | إنشاء إصدار مستقبلي وعرض سجل الإصدارات ومركز عام للنصوص النافذة | `/platform/policies` و`/policies` و`/policies/[code]` | PASS |
