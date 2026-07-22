# مصفوفة التتبع الهندسية

| Epic | الجداول/الآلات/API/الأخطاء الرئيسية | معايير القبول |
|---|---|---|
| `E01` الهوية والمصادقة والجلسات | `users`؛ `user_sessions`؛ `user_devices`؛ `mfa_methods`؛ `/v1/auth/*`؛ `AUTH_*` | `E01-AC01`, `E01-AC02`, `E01-AC03`, `E01-AC04`, `E01-AC05` |
| `E02` اعتماد المكتب والناقل | `offices`؛ `verification_cases`؛ `office_documents`؛ `office_payout_accounts`؛ `office_verification machine`؛ `VERIFICATION_*` | `E02-AC01`, `E02-AC02`, `E02-AC03`, `E02-AC04`, `E02-AC05` |
| `E03` الجغرافيا والمسارات والأسطول | `locations`؛ `routes`؛ `seat_layouts`؛ `seat_adjacencies`؛ `vehicles`؛ `drivers` | `E03-AC01`, `E03-AC02`, `E03-AC03`, `E03-AC04`, `E03-AC05` |
| `E04` إنشاء الرحلات ونشرها | `trips`؛ `trip_stops`؛ `trip_seats`؛ `trip machine`؛ `/v1/office/trips*` | `E04-AC01`, `E04-AC02`, `E04-AC03`, `E04-AC04`, `E04-AC05` |
| `E05` البحث والتوفر والتسعير | `trips`؛ `trip_seats`؛ `/v1/public/trips/search`؛ `PRICE_CHANGED` | `E05-AC01`, `E05-AC02`, `E05-AC03`, `E05-AC04`, `E05-AC05` |
| `E06` الحجز والمرافقون والمقاعد | `seat_holds`؛ `bookings`؛ `booking_passengers`؛ `seat_assignments`؛ `booking machine`؛ `SEAT_*` | `E06-AC01`, `E06-AC02`, `E06-AC03`, `E06-AC04`, `E06-AC05`, `E06-AC06`, `E06-AC07` |
| `E07` الدفع النقدي والتحويل والإلكتروني | `payment_intents`؛ `payment_transactions`؛ `manual_payment_submissions`؛ `payment machine`؛ `ledger ELECTRONIC_PAYMENT_*` | `E07-AC01`, `E07-AC02`, `E07-AC03`, `E07-AC04`, `E07-AC05`, `E07-AC06` |
| `E08` PNR والتذاكر وخدمة الزبون الذاتية | `bookings.pnr`؛ `tickets`؛ `/v1/public/bookings*`؛ `ticket machine` | `E08-AC01`, `E08-AC02`, `E08-AC03`, `E08-AC04`, `E08-AC05` |
| `E09` التعديل والإلغاء والاسترداد | `refunds`؛ `booking transitions`؛ `refund machine`؛ `REFUND_*` | `E09-AC01`, `E09-AC02`, `E09-AC03`, `E09-AC04`, `E09-AC05`, `E09-AC06` |
| `E10` الصعود والعمل دون اتصال وعدم الحضور | `boarding_events`؛ `trip_manifests`؛ `boarding machine`؛ `/boarding,/offline-sync` | `E10-AC01`, `E10-AC02`, `E10-AC03`, `E10-AC04`, `E10-AC05`, `E10-AC06` |
| `E11` تغيير البولمان والحوادث والدعم | `support_cases`؛ `support_messages`؛ `trips interrupted`؛ `URGENT_CASE_OPEN` | `E11-AC01`, `E11-AC02`, `E11-AC03`, `E11-AC04`, `E11-AC05` |
| `E12` العمولات والدفتر والتسويات | `ledger_accounts`؛ `ledger_entries`؛ `ledger_postings`؛ `commissions`؛ `settlements`؛ `LEDGER_*` | `E12-AC01`, `E12-AC02`, `E12-AC03`, `E12-AC04`, `E12-AC05`, `E12-AC06`, `E12-AC07` |
| `E13` السياسات والإعدادات والموافقات | `policy_versions`؛ `policy_acceptances`؛ `configuration_values`؛ `POLICY_*` | `E13-AC01`, `E13-AC02`, `E13-AC03`, `E13-AC04`, `E13-AC05` |
| `E14` الخصوصية والأمان ومكافحة الاحتيال | `audit_logs`؛ `risk_assessments`؛ `data_subject_requests`؛ `legal_holds`؛ `TENANT_*` | `E14-AC01`, `E14-AC02`, `E14-AC03`, `E14-AC04`, `E14-AC05`, `E14-AC06` |
| `E15` الإشعارات | `notifications`؛ `notification_deliveries`؛ `outbox_events` | `E15-AC01`, `E15-AC02`, `E15-AC03`, `E15-AC04`, `E15-AC05` |
| `E16` لوحة المنصة والرقابة | `platform endpoints`؛ `disputes`؛ `office status`؛ `settlements` | `E16-AC01`, `E16-AC02`, `E16-AC03`, `E16-AC04`, `E16-AC05` |
| `E17` الاشتراكات والباقات | `ledger subscription events`؛ `configuration plans` | `E17-AC01`, `E17-AC02`, `E17-AC03`, `E17-AC04` |
| `E18` الاستمرارية والمراقبة والإطلاق | `outbox/webhooks`؛ `backup/runbooks`؛ `recovery tests` | `E18-AC01`, `E18-AC02`, `E18-AC03`, `E18-AC04`, `E18-AC05`, `E18-AC06` |
| `E19` تجربة الاستخدام وRTL وإمكانية الوصول | `public/office/platform UX flows`؛ `policy disclosure` | `E19-AC01`, `E19-AC02`, `E19-AC03`, `E19-AC04`, `E19-AC05` |
