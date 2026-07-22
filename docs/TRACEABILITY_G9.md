# مصفوفة ربط G9 — E11 تغيير البولمان والدعم والحوادث التشغيلية

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E11-AC01 | محاكاة إصداريّة قبل التطبيق، مخزون مقاعد جديد، إغلاق المخزون السابق، منع المقعد المزدوج، حماية الطفل/المرافق، وإعادة فحص قاعدة الجنس | `test_e11_ac01_vehicle_reallocation_preserves_groups_gender_and_unique_seats` | PASS محليًا؛ قيود PostgreSQL تبقى ضمن بوابة CI |
| E11-AC02 | رفض تذكرة صحيحة يفتح P1 تلقائيًا، يجمد المقعد ويرسل تصعيدًا وAudit/Outbox | `test_e11_ac02_valid_ticket_denial_opens_p1_freezes_seat_and_escalates` | PASS |
| E11-AC03 | مهلة SLA للحالة العاجلة؛ غياب رد المكتب يصعّدها للمنصة ويسجل مخالفة غير مكررة | `test_e11_ac03_overdue_office_case_escalates_to_platform_and_records_violation` | PASS |
| E11-AC04 | تحقق احتياطي بالقائمة/PNR وهوية جزئية دون فتح دفعة جديدة أو تغيير المال | `test_e11_ac04_outage_recovery_uses_manifest_or_pnr_without_new_payment` | PASS |
| E11-AC05 | الرحلة المتوقفة تنشئ سجل حق لكل حجز، ويُرفض إغلاقها قبل حل جميع السجلات | `test_e11_ac05_interrupted_trip_cannot_complete_before_all_rights_are_resolved` | PASS |
| مخزون إصداري | `TripSeat.inventory_version` و`is_current`؛ القيود الفريدة تنطبق على المخزون الحالي فقط، ويظل التاريخ قابلًا للتدقيق | migration `trips.0004` + AC01 | PASS |
| خطة إعادة التوزيع | `TripReallocationPlan` و`TripReallocationLine` تحفظ المحاكاة والدرجة والتعارض والنتيجة قبل التطبيق | AC01 + OpenAPI | PASS |
| مجموعات الطفل/المرافق | الخوارزمية تعطي أولوية للمجموعات المحمية ولا تقبل توزيعها دون تجاور `same_unit` | AC01 | PASS |
| قاعدة الجنس | التحقق يتم على التوزيع المقترح بين الحجوزات المستقلة دون كشف بيانات الراكب الآخر | AC01 | PASS |
| التذاكر | الإسناد القديم يتحول إلى `moved` قبل إنشاء الجديد، ثم تُبطل التذكرة السابقة ويصدر Version جديد | AC01 | PASS |
| موافقة المسافر | الحجز المسترجع يعرض التغييرات المعلقة، ويسمح بقبولها أو طلب بديل أو استرداد | AC01 + `/manage-booking` build | PASS |
| Idempotency | المحاكاة والتطبيق ورد المسافر وحالات الدعم والرسائل وقرارات الحادث تحفظ النتيجة وتمنع إعادة المفتاح لطلب مختلف | اختبارات E11 المدمجة + `common.idempotency` | PASS |
| الدعم | حالات ورسائل مشتركة/داخلية، أولويات P0–P4، ملكية، حالات، SLA وViolation | AC02/AC03 + OpenAPI | PASS |
| صلاحيات التشغيل | `office.support.manage` و`platform.support.manage` و`platform.trip.incident.manage` ضمن Seed الرسمي | `seed_foundation` + clean seed | PASS |
| واجهة المكتب | تغيير البولمان، جدول التوزيع، الدعم، الردود، والتحقق الاحتياطي | ESLint + TypeScript + Next.js build | PASS |
| واجهة المنصة | طابور P1 وحل حقوق الحجوزات وإغلاق الحادث بعد استيفائها | ESLint + TypeScript + Next.js build | PASS |
| واجهة العميل | عرض التغيير الجوهري وقبول/بديل/استرداد، وفتح حالة دعم مرتبطة بالحجز | ESLint + TypeScript + Next.js build | PASS |
