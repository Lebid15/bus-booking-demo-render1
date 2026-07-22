# مصفوفة ربط G2 — E04 إنشاء الرحلات ونشرها

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E04-AC01 | فحص جاهزية المكتب والفرع والمسار والمركبة والسائق والوثائق والمخطط والسعر والنوافذ والسياسات قبل `schedule`، مع عدم حدوث أي طفرة عند الفشل | `test_e04_ac01_schedule_returns_missing_fields_and_does_not_mutate_trip` | PASS |
| Snapshot الرحلة | تثبيت السياسات والسعر وطرق الدفع والتوقفات والمقاعد داخل معاملة الجدولة | `test_schedule_captures_policy_pricing_stops_and_seat_inventory_snapshots` | PASS |
| E04-AC02 | مهمة Celery دورية وidempotent تفتح الحجز مرة واحدة عند حلول `booking_open_at` | `test_e04_ac02_booking_opens_automatically_once` | PASS محليًا؛ تكرار CI/Redis مطلوب |
| E04-AC03 | مقارنة Snapshot التغيير وتصنيفه، وإنشاء `TripChangeResponse` لكل حجز فعال وإرسال حدث إشعار عبر Outbox | `test_e04_ac03_material_time_change_creates_explicit_customer_responses` | PASS |
| E04-AC04 | منع `depart` عند ازدواج الإسناد أو وجود حالة تشغيلية عاجلة أو راكب مؤكد بلا مقعد | `test_e04_ac04_departure_is_blocked_for_confirmed_passenger_without_seat` | PASS |
| E04-AC05 | إيقاف البيع، حظر مقاعد الرحلة، نقل الحجوزات المتأثرة إلى المعالجة، وإنشاء إجراء بديل/استرداد لكل حجز | `test_e04_ac05_cancellation_stops_sales_and_starts_action_for_every_booking` | PASS؛ التنفيذ المالي الكامل يغلق في Epic المال والاسترداد |
| Tenant isolation | إنشاء وعرض وتعديل الرحلات يتم من `request.office_context` ولا يقبل `office_id` لاختيار النطاق | Services + اختبارات أساس G0/G1 | PASS |
| Optimistic concurrency | تحديث الرحلة وأوامرها تتطلب `version` مطابقًا وتزيده عند النجاح | `update_trip` و`command_trip` | PASS |
| Seat inventory | `trip_seats` ثابتة لكل رحلة، وقيد حجز مؤقت نشط واحد لكل مقعد، وقيود إسناد فريدة | migrations `trips.0001` و`bookings.0002` | PASS بنيويًا؛ PostgreSQL concurrency gate مطلوب |
| Audit / Outbox | الجدولة والنشر والفتح والتغيير والمغادرة والإلغاء تنتج Audit/Outbox بعد نجاح المعاملة | اختبارات E04 + فحص السجلات | PASS |
| API | مسارات المكتب للرحلات والأوامر وخريطة المقاعد، ومسارات سياسات المنصة والعامة | `docs/evidence/G2-trips/openapi-generated.yaml` | PASS؛ 0 schema errors |
| واجهات التشغيل | صفحة رحلات المكتب وصفحة سياسات المنصة وروابط لوحتي التحكم | Next.js production build | PASS |
