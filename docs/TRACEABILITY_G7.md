# مصفوفة ربط G7 — E09 تعديل الحجز والإلغاء والاسترداد

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E09-AC01 | Quote موقّع ومحدود الصلاحية يُحسب من `booking.policy_snapshot` والأسعار المثبتة، مع رقم نسخة الحجز والركاب المختارين | `test_e09_ac01_cancellation_quote_uses_frozen_booking_policy_snapshot` | PASS |
| E09-AC02 | منع الإلغاء أو الاستبدال بعد الصعود الفعلي وإرجاع `PASSENGER_ALREADY_BOARDED` | `test_e09_ac02_boarded_passenger_cannot_be_cancelled` | PASS |
| E09-AC03 | إلغاء راكب واحد ذريًا، تحرير مقعده فقط، إبطال QR الخاص به، خفض إجمالي الحجز، تعديل العمولة، وإنشاء Refund مستقل | `test_e09_ac03_partial_cancellation_releases_only_selected_seat_and_refunds_it` | PASS |
| E09-AC04 | منع منشئ طلب الاسترداد من اعتماده، وفرض MFA حديث فوق الحد المالي | `test_e09_ac04_refund_requester_cannot_approve_own_high_value_refund` | PASS |
| E09-AC05 | فحص Chargeback المفتوح قبل اعتماد المبلغ ومنع التعويض المزدوج | `test_e09_ac05_open_chargeback_blocks_refund_and_double_compensation` | PASS |
| E09-AC06 | استبدال الراكب يعيد فحص قاعدة جنس المقعد المجاور قبل تثبيت الجنس الجديد | `test_e09_ac06_passenger_gender_replacement_rechecks_adjacency` | PASS |
| عقد API العام | حساب Quote واستهلاكه مع Manage Token و`Idempotency-Key`، وإعادة Booking محدث وفق العقد الرسمي | `test_public_cancellation_api_contract_is_idempotent` + OpenAPI generated | PASS |
| تغيير الراكب | أمر مكتبي محكوم بالصلاحية والعزل والتدقيق، يعيد إصدار التذكرة عند الحجز المؤكد | `replace_booking_passenger` + اختبار AC06 | PASS |
| تغيير المقعد | قفل المقعد الهدف، منع Hold/Assignment متعارض، إعادة فحص التجاور، إبطال وإعادة إصدار Ticket | `change_booking_seat` + مراجعة الخدمة | PASS |
| Idempotency أوامر المكتب | إعادة أمر التعديل نفسه آمنة، وتغيير الحمولة بالمفتاح نفسه يرفض | `office_booking_change` idempotency scope | PASS تطبيقي |
| Quote النزاهة | HMAC، مدة صلاحية، نسخة الحجز، إعادة حساب قبل التنفيذ، ورفض Quote قديم أو محرّف | `CANCELLATION_QUOTE_*` + اختبارات API/الخدمة | PASS |
| Refund workflow | Requested → Under review → Approved → Processing → Succeeded/Failed، مع Audit وOutbox | `command_refund` + اختبار AC03 | PASS |
| Ledger | قيد اعتماد يحول Customer Funds إلى Refund Payable، وقيد صرف يعكسه إلى النقد/PSP | اختبار AC03 و`assert_entry_balanced` | PASS محليًا؛ Trigger PostgreSQL ضمن CI |
| Commission | إعادة حساب العمولة من إجمالي الحجز بعد الإلغاء الجزئي أو عكسها عند الإلغاء الكامل | اختبار AC03 | PASS |
| واجهة العميل | اختيار الركاب، عرض Quote، تأكيد الإلغاء، تحديث التذاكر وحالة المقاعد | ESLint + TypeScript + Next.js build | PASS |
| واجهات التشغيل | `/office/refunds` و`/platform/refunds` لعرض دورة الاعتماد وضوابط Chargeback | Next.js build + API permissions | PASS تأسيسي |
