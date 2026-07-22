# مصفوفة ربط G8 — E10 الصعود وManifest والعمل دون اتصال

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E10-AC01 | قفل الرحلة والراكب والتذكرة داخل معاملة واحدة، وتحويل Ticket إلى `used` مرة واحدة | `test_e10_ac01_postgresql_concurrent_qr_scan_records_boarded_once` | PASS تصميميًا ومحليًا؛ اختبار التزامن إلزامي على PostgreSQL 18 |
| E10-AC02 | تحقق يدوي بالراكب مع سبب إلزامي، `manual_check` event وAudit | `test_e10_ac02_manual_check_boards_with_reason_and_audit` | PASS |
| E10-AC03 | مهمة No-show لا تمس الراكب المرفوض أو الحالة العاجلة، وتصدر Audit وOutbox للقرار الآلي | `test_e10_ac03_no_show_job_skips_denied_boarding_review` و`test_due_no_show_marks_only_eligible_unarrived_passenger` | PASS |
| E10-AC04 | حزمة مشفرة وموقعة ومقيدة بالجهاز والمدة ونسخة الرحلة؛ مزامنة أحداث Idempotent وتخزين التعارضات | `test_e10_ac04_offline_sync_is_idempotent_and_surfaces_conflicts` | PASS |
| E10-AC05 | عكس الصعود بعد المغادرة مرفوض دون موافقة منصة مخصصة أحادية الاستخدام | `test_e10_ac05_reverse_after_departure_requires_admin_approval` | PASS |
| E10-AC06 | Manifest إصداري Append-only ببصمة SHA-256؛ نسخة عند إغلاق الصعود ونسخة نهائية عند المغادرة، وأي عبث يُكشف | `test_e10_ac06_closed_and_final_manifests_are_hashed_and_tamper_evident` | PASS |
| QR أحادي الاستخدام | رفض المسح الثاني بإرجاع `TICKET_ALREADY_USED` دون إنشاء حدث ثانٍ | `test_boarding_qr_is_single_use_and_second_scan_is_rejected` | PASS |
| آلة الحالة | منع إرجاع راكب boarded إلى arrived أو أي انتقال رجوعي خارج المسار المحكوم | `test_boarding_state_cannot_regress_after_successful_scan` | PASS |
| Idempotency أوامر الصعود | إعادة المفتاح والحمولة نفسها تعيد النتيجة دون أثر إضافي، وإعادة المفتاح لحمولة أخرى تُرفض | `test_boarding_command_idempotency_replays_and_rejects_payload_reuse` | PASS |
| Idempotency Offline | إعادة إنشاء الحزمة أو إعادة طلب المزامنة تعيد النتيجة نفسها؛ مفتاح جديد مع حدث قديم يُسجل Duplicate | اختبار AC04 + `IdempotencyKey` scopes | PASS |
| نزاهة التذاكر في Manifest | اختيار أحدث إصدار نشط/مستخدم لكل راكب وعدم إظهار نسخة قديمة مبطلة | `_manifest_payload` + مراجعة الخدمة | PASS |
| عقد API | أربعة مسارات رسمية للمسح وManifest والحزمة والمزامنة، مع سياق مكتب وصلاحية وIdempotency | OpenAPI generated | PASS |
| واجهة المكتب | QR، تحقق يدوي، قائمة Manifest، تنزيل حزمة الجهاز، مزامنة JSON وعرض التعارضات | ESLint + TypeScript + Next.js build | PASS |
| قاعدة فارغة | إعداد `DATABASE_URL=sqlite:///...` أصبح يحترم المسار، وتطبق جميع المهاجرات على ملف جديد | `clean-migration.log` | PASS |
