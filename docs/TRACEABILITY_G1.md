# مصفوفة ربط G1 — اعتماد المكاتب والجغرافيا والأسطول

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E02-AC01 | فحص اكتمال بيانات المكتب والوثائق قبل `submitted` داخل معاملة ذرية | `test_e02_ac01_incomplete_verification_cannot_be_submitted` | PASS |
| E02-AC02 | ملف `enhanced` يمنع المراجع الأول من الاعتماد النهائي | `test_e02_ac02_enhanced_verification_requires_distinct_final_approver` | PASS |
| E02-AC03 | وثيقة مكتب حرجة منتهية تمنع الإسناد لرحلة جديدة | `test_e02_ac03_expired_critical_office_document_blocks_new_trip_assignment` | PASS |
| E02-AC04 | MFA حديث، اعتماد ثانٍ، Cooling period، إشعار للحساب السابق، تفعيل مجدول | `test_e02_ac04_payout_change_requires_mfa_dual_approval_cooling_and_notification` | PASS |
| E02-AC05 | حالات المكتب وحارس الجاهزية منفذة؛ إخفاء الرحلات العامة يربط عند بناء E04/E05 | لا توجد رحلات بعد | CONTRACT READY / E2E DEFERRED |
| E03-AC01 | كل اتجاه Route مستقل ولا ينشأ العكس ضمنيًا | `test_e03_ac01_reverse_direction_is_not_inferred` | PASS |
| E03-AC02 | موضع ورمز فريدان لكل مقعد مع adjacency صريحة | `test_e03_ac02_duplicate_seat_position_is_rejected` | PASS |
| E03-AC03 | علاقة `aisle` مستقلة ولا تتحول إلى `same_unit` | `test_e03_ac03_across_aisle_is_not_same_unit` | PASS |
| E03-AC04 | حالة المركبة ووثائقها ورخصة السائق تمنع الإسناد | `test_e03_ac04_inactive_or_expired_resources_are_not_assignable` | PASS |
| E03-AC05 | التعديل ينشئ إصدارًا جديدًا ويحافظ على مرجع المركبة للإصدار القديم | `test_e03_ac05_layout_change_creates_version_and_keeps_existing_vehicle_snapshot_reference` | PASS جزئي؛ Snapshot الرحلة يكتمل في E04 |
| Tenant isolation | جميع موارد المكتب تُرشح من `request.office_context` | Service filters + اختبارات G0 | PASS |
| Sensitive sessions | جلسة MFA تحمل دليلًا خادميًا محدود العمر | migration `identity.0002` + E02-AC04 | PASS |
