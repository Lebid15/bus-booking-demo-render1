# مصفوفة ربط G4 — E06/E07 تثبيت الحجز والمرافقين والمقاعد

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E06-AC01 | قفل الرحلة والـHolds وTripSeat داخل معاملة واحدة، مع قيد جزئي لإسناد نشط واحد للمقعد والراكب | `test_e06_ac01_parallel_confirmation_creates_only_one_active_assignment` | جاهز لـPostgreSQL CI؛ SKIP محليًا على SQLite |
| E06-AC02 | فحص adjacency من نوع `same_unit` مقابل الإسنادات النشطة لحجوزات أخرى، وإرجاع `SEAT_GENDER_CONFLICT` دون تفاصيل تكشف الجنس الآخر | `test_e06_gender_conflict_is_private_across_bookings_but_allowed_inside_one_booking` | PASS |
| E06-AC03 | عند وجود المقعدين داخل الحجز نفسه لا تطبق قاعدة المنع بين الجنسين | الاختبار نفسه — شق الحجز المختلط | PASS |
| E06-AC04 | حفظ `passenger_grouping` وفيه أزواج الطفل/المرافق و`requires_reassignment_review` لمن لا يملك مرافقًا مجاورًا | `test_e06_child_guardian_group_is_snapshotted_and_boarding_states_remain_independent` | FOUNDATION PASS؛ تطبيق إعادة توزيع البولمان الكامل يتبع E11 |
| E06-AC05 | رفض Hold منتهي قبل إنشاء Booking أو Passenger أو SeatAssignment، وإتاحة المقعد للبيع بعد تنظيف الانتهاء | `test_e06_expired_hold_is_rejected_without_consuming_resold_seat` | PASS |
| E06-AC06 | حفظ Quote والسعر والسياسات والعمولة والمهلة وإصدارات القبول داخل Booking، وعدم تأثرها بتعديل Trip لاحقًا | `test_e06_hold_is_consumed_atomically_and_booking_snapshots_are_frozen` | PASS |
| E06-AC07 | حالة الصعود محفوظة لكل `BookingPassenger` بصورة مستقلة | `test_e06_child_guardian_group_is_snapshotted_and_boarding_states_remain_independent` | PASS |
| E07 تدفق الحجز العام | `POST /v1/public/bookings` يستهلك Hold ويثبت الاتصال والركاب وطريقة الدفع ويعيد الحجز النهائي | `test_public_booking_api_is_idempotent_and_returns_pnr_and_manage_token` | PASS |
| مهلة الدفع | `manual_transfer` ينتج `awaiting_payment` بمهلة مثبتة؛ `office_cash` يسمح بحجز مؤكد غير مدفوع | `test_manual_transfer_booking_waits_for_payment_and_keeps_deadline_snapshot` | PASS |
| قبول السياسات | مقارنة صارمة بين الإصدارات المقبولة والإصدارات المثبتة للرحلة؛ عدم التطابق يعيد 428 | `_validate_policy_acceptance` + OpenAPI | PASS |
| Idempotency | إعادة المفتاح والجسم تعيد Booking وPNR نفسيهما، ولا تحفظ Manage Token كنص صريح في سجل Idempotency | `test_public_booking_api_is_idempotent_and_returns_pnr_and_manage_token` | PASS |
| E08-AC01 — شريحة تأسيسية | إصدار PNR عشوائي ورمز إدارة HMAC والتحقق منه عبر hash | `manage_token_matches` و`test_e06_hold_is_consumed_atomically_and_booking_snapshots_are_frozen` | PARTIAL؛ إصدار التذاكر وQR يتبع E08 |
| واجهة PUB-09 | شاشة الحجز تعرض بيانات الاتصال والدفع وقبول السياسات ثم PNR والحالة والمقاعد والإجمالي | Next.js lint/typecheck/build | PASS |
