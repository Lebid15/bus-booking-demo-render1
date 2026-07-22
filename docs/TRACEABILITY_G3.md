# مصفوفة ربط G3 — E05 البحث والتوفر والحجز المؤقت

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E05-AC01 | البحث حسب الأصل والوجهة والتاريخ وعدد الركاب، مع تفسير التاريخ وفق `office.timezone` وإظهار الرحلات المفتوحة فقط | `test_e05_ac01_search_uses_office_local_date_and_only_bookable_trips` | PASS |
| E05-AC02 | `from_price` صادق يجمع السعر والرسوم المعلنة، ويعيد العملة وطرق الدفع وملخص سياسة الإلغاء و`quote_version` | `test_e05_ac02_search_discloses_honest_price_fees_and_policy` | PASS |
| E05-AC03 | خريطة المقاعد استشارية فقط؛ إنشاء الـHold يعيد قفل الرحلة والمقاعد ويفحص الإسنادات والـHolds النشطة داخل معاملة | `test_e05_ac03_map_does_not_authorize_stale_seat_selection` | PASS محليًا؛ اختبار PostgreSQL المتوازي إلزامي في CI |
| E05-AC04 | البحث والـHold لا يستدعيان أي مزود إشعارات مباشر؛ النجاح التجاري يكتب Outbox محليًا وتتم القناة خارجيًا بصورة غير متزامنة | تصميم الخدمة + `booking.seat_hold.created` | PASS معماريًا |
| E05-AC05 | الاستعلام العام يسمح فقط بحالات المكتب المقبولة ويستبعد `no_new_bookings`, `restricted`, `suspended` | `test_e05_ac05_restricted_office_trips_are_hidden` | PASS |
| E06-AC01 — شريحة مبكرة | قفل `Trip` و`TripSeat` مع قيد جزئي لمقعد ذي Hold نشط واحد فقط؛ اختبار متوازي بمستخدمين | `test_e06_ac01_postgresql_concurrent_hold_has_single_winner` | جاهز لـPostgreSQL CI؛ SKIP محليًا على SQLite |
| E06-AC05 — شريحة مبكرة | انتهاء الـHold بمهمة Celery Beat والاستبعاد الفوري من التوفر، وعدم اعتبار Hold منتهي صالحًا | `test_hold_release_and_expiry_restore_availability` | PASS |
| Idempotency | إعادة الطلب بنفس المفتاح والجسم تعيد نفس رمز الـHold دون إنشاء صف إضافي أو استهلاك حصة Rate limit ثانية؛ تغيير الجسم بالمفتاح نفسه يرفض | `test_public_hold_revalidates_inventory_and_is_idempotent`, `test_idempotent_hold_replay_does_not_consume_rate_limit_twice` | PASS |
| ملكية الرمز | رمز جماعي `batch.secret` لا يخزن كنص صريح؛ كل صف يحتفظ ببصمة مرتبطة بالمقعد، والتحرير يتحقق من كل البصمات | `release_public_seat_hold`, `hold_belongs_to_token` | PASS |
| API contract | البحث والمواقع والتفاصيل والخريطة وإنشاء الـHold وتحريره تعمل عبر HTTP | `test_public_api_search_hold_and_release_contract` + OpenAPI | PASS |
| واجهات عامة | نموذج بحث فعلي، بطاقات نتائج، صفحة خريطة مقاعد، بيانات ركاب، إنشاء Hold وعرض الإجمالي والمهلة | Next.js lint/typecheck/build | PASS |
