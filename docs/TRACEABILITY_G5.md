# مصفوفة ربط G5 — E08 التذاكر وQR والخدمة الذاتية

| المرجع | التنفيذ | الاختبار/الدليل | الحالة |
|---|---|---|---|
| E08-AC01 | إصدار PNR ورمز إدارة سابقًا، وإضافة Ticket نشط مستقل لكل راكب مؤكد مع `version_no` وQR موقع | `test_e08_ac01_confirmed_guest_booking_issues_ticket_per_passenger` | PASS |
| شرط الإصدار | الحجز `awaiting_payment` لا يصدر تذكرة حتى يصبح مؤكدًا | `test_e08_awaiting_payment_booking_does_not_issue_active_ticket` | PASS |
| E08-AC02 | Lookup بالـPNR ووسيلة الاتصال، Rate limit بحسب العميل، ونفس 404 عند PNR أو verifier خاطئ | `test_e08_ac02_lookup_is_generic_and_rate_limited` | PASS |
| E08-AC03 | خدمة ذرية تبطل التذكرة النشطة وتصدر Version جديدًا، والـQR القديم يرفض | `test_e08_ac03_reissue_revokes_old_qr_and_increments_version` | CORE PASS؛ ربطها بأوامر التعديل العامة يتبع E09 |
| E08-AC04 | التذكرة وQR متاحان مباشرة من صفحة النجاح والاسترجاع، دون الاعتماد على نجاح البريد | `test_e08_ac04_ticket_document_and_qr_are_available_without_email` | PASS |
| E08-AC05 | ربط حجز ضيف بالحساب عند تطابق هاتف/بريد موثق، ثم ظهوره في `/v1/me/bookings` دون نسخة جديدة | `test_e08_ac05_verified_customer_links_guest_booking_without_copy` | PASS |
| سلامة QR | HMAC للحمولة، SHA-256 للرمز في DB، مقارنة التوقيع المخزن، ومنع مستند التذكرة دون Manage Token | `test_e08_ticket_qr_is_tamper_evident_and_document_requires_manage_token` | PASS |
| API إدارة الضيف | `POST /v1/public/bookings/lookup` و`GET /v1/public/bookings/{pnr}` | OpenAPI generated + tests | PASS |
| API الحساب | `GET /v1/me/bookings` و`POST /v1/me/bookings/link` | الاختبار AC05 | PASS |
| مستند وQR | HTML ذاتي قابل للطباعة/الحفظ PDF وSVG QR محميان برمز الإدارة | اختبار AC04 + Next.js build | PASS |
| شاشة PUB-11 | `/manage-booking` تعرض الرحلة والحالة والركاب وQR والتذكرة لكل راكب | ESLint + TypeScript + Next.js production build | PASS |
