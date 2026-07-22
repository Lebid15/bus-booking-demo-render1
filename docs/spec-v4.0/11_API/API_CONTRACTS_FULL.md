# عقود API التنفيذية

المرجع الآلي الكامل هو `openapi.yaml`. هذه الوثيقة تضيف القواعد التي لا تكفي OpenAPI وحدها لتمثيلها.

## قواعد البروتوكول

- Prefix: `/v1`.
- JSON فقط باستثناء رفع الملفات المباشر الموقّع.
- المال نص decimal، لا float.
- كل Mutation حساس يستخدم `Idempotency-Key` ويعيد النتيجة نفسها عند تكرار الطلب المطابق.
- كل استجابة تحمل `X-Request-ID`.
- PATCH يستخدم optimistic `version`; التعارض يعيد `VERSION_CONFLICT`.
- Pagination cursor-based للقوائم الكبيرة.
- وقت UTC ISO-8601؛ العرض المحلي مسؤولية العميل وفق timezone.
- المكتب لا يرسل `office_id` لتحديد نطاقه؛ يستنتج من العضوية/السياق.

## حدود المعاملات

1. إنشاء الحجز: قفل المقاعد + فحص الجنس + snapshots + assignment + booking + commission expected + outbox في معاملة واحدة.
2. نجاح الدفع: provider event dedupe + transaction + booking totals + ledger + confirmation event في معاملة واحدة.
3. الصعود: ticket lock + status + boarding event في معاملة واحدة.
4. الاسترداد والتسوية: ledger/postings والكيان التجاري في معاملة واحدة، والاتصال بالمزود خارجها عبر outbox/workflow.

## Endpoint Inventory

| Method | Path | العملية |
|---|---|---|
| `GET` | `/v1/public/locations` | قائمة نقاط الانطلاق والوصول |
| `GET` | `/v1/public/trips/search` | البحث عن الرحلات |
| `GET` | `/v1/public/trips/{trip_id}` | تفاصيل الرحلة والسياسات |
| `GET` | `/v1/public/trips/{trip_id}/seats` | خريطة المقاعد المتاحة |
| `POST` | `/v1/public/trips/{trip_id}/seat-holds` | إنشاء حجز مؤقت للمقاعد |
| `POST` | `/v1/public/seat-holds/{hold_token}/release` | تحرير الحجز المؤقت |
| `POST` | `/v1/public/bookings` | إنشاء الحجز النهائي |
| `POST` | `/v1/public/bookings/lookup` | استرجاع حجز كضيف |
| `GET` | `/v1/public/bookings/{pnr}` | عرض الحجز عبر رمز الإدارة |
| `GET` | `/v1/public/bookings/{pnr}/cancellation-quote` | حساب الإلغاء قبل التنفيذ |
| `POST` | `/v1/public/bookings/{pnr}/cancel` | طلب إلغاء الحجز |
| `POST` | `/v1/public/bookings/{pnr}/payments` | بدء عملية دفع |
| `POST` | `/v1/public/payment-intents/{intent_id}/manual-transfer` | رفع بيانات تحويل يدوي |
| `POST` | `/v1/public/bookings/{pnr}/support-cases` | فتح حالة دعم للحجز |
| `POST` | `/v1/auth/login` | تسجيل الدخول |
| `POST` | `/v1/auth/mfa/verify` | إكمال MFA |
| `GET` | `/v1/me/bookings` | حجوزاتي |
| `GET` | `/v1/me/bookings/{booking_id}` | تفاصيل حجز الحساب |
| `GET` | `/v1/me/sessions` | الجلسات والأجهزة |
| `POST` | `/v1/me/data-export` | طلب تصدير البيانات |
| `POST` | `/v1/me/delete-account` | طلب حذف الحساب |
| `GET` | `/v1/office/context` | سياق المكتب والصلاحيات |
| `GET` | `/v1/office/trips` | قائمة رحلات المكتب |
| `POST` | `/v1/office/trips` | إنشاء رحلة |
| `GET` | `/v1/office/trips/{trip_id}` | تفاصيل رحلة المكتب |
| `PATCH` | `/v1/office/trips/{trip_id}` | تعديل رحلة مسموح |
| `POST` | `/v1/office/trips/{trip_id}/commands` | تنفيذ انتقال حالة الرحلة |
| `GET` | `/v1/office/trips/{trip_id}/seat-map` | خريطة المقاعد الحية للمكتب |
| `GET` | `/v1/office/trips/{trip_id}/bookings` | حجوزات الرحلة |
| `POST` | `/v1/office/trips/{trip_id}/bookings` | إنشاء حجز من المكتب |
| `GET` | `/v1/office/bookings/{booking_id}` | تفاصيل حجز المكتب |
| `POST` | `/v1/office/bookings/{booking_id}/payments/cash` | تسجيل دفع في المكتب |
| `POST` | `/v1/office/manual-payments/{submission_id}/verify` | التحقق من تحويل يدوي |
| `POST` | `/v1/office/trips/{trip_id}/boarding` | تنفيذ أمر صعود |
| `GET` | `/v1/office/trips/{trip_id}/manifest` | قائمة ركاب الرحلة |
| `POST` | `/v1/office/trips/{trip_id}/offline-package` | توليد حزمة صعود دون اتصال |
| `POST` | `/v1/office/trips/{trip_id}/offline-sync` | مزامنة أحداث الصعود غير المتصلة |
| `GET` | `/v1/office/refunds` | طلبات الاسترداد |
| `POST` | `/v1/office/refunds/{refund_id}/commands` | مراجعة/اعتماد الاسترداد |
| `GET` | `/v1/office/settlements` | تسويات المكتب |
| `GET` | `/v1/office/configuration` | إعدادات المكتب الفعالة |
| `PATCH` | `/v1/office/configuration` | تعديل إعدادات المكتب |
| `GET` | `/v1/office/support-cases` | صندوق حالات المكتب |
| `GET` | `/v1/platform/offices` | إدارة المكاتب |
| `POST` | `/v1/platform/offices/{office_id}/verification/commands` | قرارات تحقق المكتب |
| `POST` | `/v1/platform/offices/{office_id}/status` | تقييد أو تعليق المكتب |
| `GET` | `/v1/platform/disputes` | قائمة النزاعات |
| `POST` | `/v1/platform/disputes/{dispute_id}/commands` | تنفيذ قرار نزاع |
| `GET` | `/v1/platform/settlements` | جميع التسويات |
| `POST` | `/v1/platform/settlements` | إنشاء دورة تسوية |
| `POST` | `/v1/platform/settlements/{settlement_id}/commands` | انتقالات التسوية |
| `GET` | `/v1/platform/policies` | إصدارات السياسات |
| `POST` | `/v1/platform/policies` | إنشاء إصدار سياسة |
| `GET` | `/v1/platform/configuration` | إعدادات المنصة |
| `PATCH` | `/v1/platform/configuration` | تعديل إعدادات المنصة |
| `POST` | `/v1/webhooks/payments/{provider_code}` | Webhook مزود الدفع |
| `GET` | `/v1/public/policies/{policy_code}` | عرض السياسة النافذة للزبون |
| `POST` | `/v1/files/upload-intents` | إنشاء رابط رفع خاص ومحدود |
| `POST` | `/v1/files/{file_id}/complete` | إكمال رفع ملف وبدء الفحص |
| `GET` | `/v1/office/branches` | قائمة فروع المكتب |
| `POST` | `/v1/office/branches` | إنشاء فرع مكتب |
| `PATCH` | `/v1/office/branches/{branch_id}` | تعديل فرع المكتب |
| `GET` | `/v1/office/staff` | موظفو المكتب وصلاحياتهم |
| `POST` | `/v1/office/staff` | دعوة موظف إلى المكتب |
| `PATCH` | `/v1/office/staff/{membership_id}` | تعديل دور أو حالة موظف |
| `GET` | `/v1/office/seat-layouts` | مخططات مقاعد المكتب |
| `POST` | `/v1/office/seat-layouts` | إنشاء مخطط مقاعد |
| `GET` | `/v1/office/seat-layouts/{layout_id}` | تفاصيل مخطط مقاعد |
| `PATCH` | `/v1/office/seat-layouts/{layout_id}` | إنشاء إصدار معدل من المخطط |
| `GET` | `/v1/office/vehicles` | قائمة البولمانات |
| `POST` | `/v1/office/vehicles` | إضافة بولمان |
| `PATCH` | `/v1/office/vehicles/{vehicle_id}` | تعديل حالة أو بيانات البولمان |
| `GET` | `/v1/office/drivers` | قائمة السائقين |
| `POST` | `/v1/office/drivers` | إضافة سائق |
| `PATCH` | `/v1/office/drivers/{driver_id}` | تعديل السائق |
| `GET` | `/v1/office/support-cases/{case_id}/messages` | رسائل حالة الدعم للمكتب |
| `POST` | `/v1/office/support-cases/{case_id}/messages` | الرد على حالة دعم |
| `GET` | `/v1/office/subscription` | اشتراك المكتب الحالي |
| `POST` | `/v1/office/subscription/change-request` | طلب تغيير باقة المكتب |
| `GET` | `/v1/office/reports/trips` | تقرير الرحلات |
| `GET` | `/v1/office/reports/sales` | تقرير المبيعات والعمولات |
| `GET` | `/v1/office/reports/passengers` | تقرير الركاب والصعود |
| `GET` | `/v1/office/notifications` | إشعارات موظف المكتب |
| `GET` | `/v1/platform/locations` | إدارة المواقع والنقاط |
| `POST` | `/v1/platform/locations` | إنشاء موقع أو نقطة |
| `PATCH` | `/v1/platform/locations/{location_id}` | تعديل موقع أو نقطة |
| `GET` | `/v1/platform/routes` | إدارة الخطوط |
| `POST` | `/v1/platform/routes` | إنشاء خط |
| `PATCH` | `/v1/platform/routes/{route_id}` | تعديل حالة أو نقاط الخط |
| `GET` | `/v1/platform/subscription-plans` | قائمة باقات الاشتراك |
| `POST` | `/v1/platform/subscription-plans` | إنشاء باقة اشتراك |
| `PATCH` | `/v1/platform/subscription-plans/{plan_id}` | إصدار/تعديل باقة اشتراك |
| `POST` | `/v1/platform/offices/{office_id}/subscription` | تفعيل أو تغيير اشتراك مكتب |
| `GET` | `/v1/platform/commission-profiles` | ملفات العمولات |
| `POST` | `/v1/platform/commission-profiles` | إنشاء ملف عمولة |
| `PATCH` | `/v1/platform/commission-profiles/{profile_id}` | إصدار تعديل ملف عمولة |
| `GET` | `/v1/platform/refunds` | جميع طلبات الاسترداد |
| `GET` | `/v1/platform/chargebacks` | اعتراضات مزود الدفع |
| `GET` | `/v1/platform/support-cases` | صندوق دعم المنصة |
| `GET` | `/v1/platform/support-cases/{case_id}/messages` | رسائل حالة دعم المنصة |
| `POST` | `/v1/platform/support-cases/{case_id}/messages` | رد المنصة على حالة دعم |
| `GET` | `/v1/platform/incidents` | حوادث الرحلات والنظام |
| `POST` | `/v1/platform/incidents` | فتح حادث |
| `GET` | `/v1/platform/violations` | مخالفات المكاتب |
| `POST` | `/v1/platform/violations` | تسجيل مخالفة مكتب |
| `GET` | `/v1/platform/audit-logs` | البحث في سجل التدقيق |
| `GET` | `/v1/platform/risk-assessments` | مراجعات المخاطر |
| `GET` | `/v1/platform/reports/overview` | لوحة مؤشرات المنصة |
