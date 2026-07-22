# منصة حجز البولمن

مستودع التنفيذ الرسمي للمواصفة `bus-booking-final-spec v4.0`.

## الحالة الحالية

- Gate: **G19 — PostgreSQL 18 and launch-readiness hardening**.
- Release: **v0.19.1 RC2**.
- المنفذ: **19 من 19 Epic** و**103 من 103 معيار قبول** ضمن المواصفة v4.0.
- PostgreSQL 18.4: **139 من 139 اختبارًا ناجحًا**.
- SQLite compatibility: **135 ناجحة و4 مؤجلة حصريًا لـPostgreSQL**، وقد نجحت الأربعة ضمن مجموعة PostgreSQL.
- PostgreSQL وRedis وCelery وAPI Smoke والنسخ والاستعادة وPITR: **PASS**؛ ضغط محلي متزامن **600/600** دون أخطاء.
- عقد API: **132 مسارًا و157 عملية** دون أخطاء أو تحذيرات.
- واجهة Next.js: **40 مسارًا**، وتشغيل Production فعلي لخمسة مسارات RTL أساسية، ونجاح تدقيق npm المتصل دون ثغرات.
- مصدر الحقيقة: `docs/spec-v4.0/`.
- تقرير الإغلاق: `docs/FINAL_CLOSURE_STATUS.md`.
- أدلة G19: `docs/evidence/G19-launch-readiness/`.

الحزمة مرشح إصدار قوي ومكتمل برمجيًا، بينما يبقى إطلاق Production مشروطًا ببيئة Staging الحقيقية، الخدمات الخارجية، الاختبارات الأمنية المتصلة، الاعتمادات القانونية والتجارية، والـPilot التشغيلي.

## التشغيل المحلي

```bash
cp .env.example .env
# أنشئ مفتاح Fernet وضعه في MFA_ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build
```

الخدمات:

- Public/Office/Platform web: `http://localhost:3000`
- API: `http://localhost:8000`
- API schema: `http://localhost:8000/api/schema/`
- Health: `http://localhost:8000/health/live` و`/health/ready`

## أوامر الجودة

```bash
make validate-spec
make backend-check
make backend-test
make frontend-check
```

## المبادئ الملزمة

1. PostgreSQL هو مصدر الحقيقة للمقاعد والمال.
2. المكتب لا يرسل `office_id` لتحديد نطاقه؛ السياق مشتق من الجلسة والعضوية.
3. أي جلسة ملغاة تُرفض فورًا عند كل طلب.
4. الآثار الخارجية تمر عبر Outbox بعد نجاح المعاملة.
5. كل مهمة ترتبط بـEpic ومعيار قبول ودليل اختبار.
6. الجدولة تثبّت Snapshot السياسات والأسعار والتوقفات والمقاعد؛ لا تعاد كتابة الحقيقة التاريخية من بيانات حية لاحقة.
7. لون المقعد في الواجهة استشاري؛ الخادم يعيد القفل والفحص قبل إنشاء أي Hold أو إسناد.

## الخدمة الذاتية للحجز

- استرجاع الحجز: `http://localhost:3000/manage-booking`
- Lookup API: `POST /v1/public/bookings/lookup`
- إدارة عبر الرمز: `GET /v1/public/bookings/{pnr}?manage_token=...`
- لكل راكب QR وتذكرة مستقلة، ولا يصدر Ticket للحجز غير المؤكد.


## الدفع والمالية

- بدء الدفع: `POST /v1/public/bookings/{pnr}/payments`
- رفع تحويل: `POST /v1/public/payment-intents/{intent_id}/manual-transfer`
- قبض المكتب: `POST /v1/office/bookings/{booking_id}/payments/cash`
- مراجعة التحويل: `POST /v1/office/manual-payments/{submission_id}/verify`
- Webhook المزود: `POST /v1/webhooks/payments/{provider_code}` — يثبت الحدث في Inbox ثم تعالجه Celery بصورة Idempotent
- كل حركة ناجحة تسجل في Ledger متوازن، ولا يعاد تأكيد مقعد مباع بسبب دفع متأخر.


## الصعود والعمل دون اتصال

- بوابة المكتب: `http://localhost:3000/office/boarding`
- تسجيل الصعود: `POST /v1/office/trips/{trip_id}/boarding`
- Manifest قابل للتحقق: `GET /v1/office/trips/{trip_id}/manifest`
- حزمة جهاز مشفرة وموقعة: `POST /v1/office/trips/{trip_id}/offline-package`
- مزامنة Idempotent مع حفظ التعارضات: `POST /v1/office/trips/{trip_id}/offline-sync`
- QR أحادي الاستخدام، والتحقق اليدوي يتطلب سببًا ويسجل Audit.
- إغلاق الصعود ينشئ Manifest ذا بصمة، والمغادرة تنشئ النسخة النهائية.

## تغيير البولمان والدعم التشغيلي

- محاكاة تغيير البولمان: `POST /v1/office/trips/{trip_id}/vehicle-change/preview`
- التطبيق الذري: `POST /v1/office/trips/{trip_id}/vehicle-change/apply`
- واجهة المكتب: `http://localhost:3000/office/reallocation`
- الدعم والتحقق الاحتياطي: `http://localhost:3000/office/support`
- مركز الحوادث: `http://localhost:3000/platform/incidents`
- المخزون إصداري، والتذاكر القديمة تُبطل ويصدر بديل، ولا تُغلق الرحلة المتوقفة قبل معالجة حقوق جميع الحجوزات.

## العمولات والدفتر والتسويات

- تسويات المكتب: `http://localhost:3000/office/settlements`
- مركز مالية المنصة: `http://localhost:3000/platform/finance`
- عرض تسويات المكتب: `GET /v1/office/settlements`
- إنشاء وإدارة التسويات: `GET/POST /v1/platform/settlements` و`POST /v1/platform/settlements/{settlement_id}/commands`
- ملفات العمولة الإصدارية: `GET/POST /v1/platform/commission-profiles`
- لا تُخلط العملات، ولا يُجمّد إلا مبلغ الحجز المتنازع عليه، ولا يستطيع منشئ التسوية اعتمادها.
- القيود المنشورة لا تُعدل؛ التصحيح يتم بقيد Reversal/Adjustment جديد.

## السياسات والإعدادات والموافقات

- إعدادات المكتب: `http://localhost:3000/office/settings`
- إعدادات المنصة والاعتماد المزدوج: `http://localhost:3000/platform/settings`
- إدارة إصدارات السياسات: `http://localhost:3000/platform/policies`
- مركز السياسات العام: `http://localhost:3000/policies`
- API إعداد المكتب: `GET/PATCH /v1/office/configuration`
- API إعداد المنصة: `GET/PATCH /v1/platform/configuration`
- كل تغيير إصداري وله وقت نفاذ وسبب وAudit before/after؛ قيم الرحلات المؤثرة تُثبت عند الجدولة.
- لا يؤكد الحجز دون قبول جميع إصدارات السياسات المطلوبة، وتُحفظ الموافقة حسب الإصدار واللغة والكيان والوقت.


## الخصوصية والأمان ومكافحة الاحتيال

- حقوق بيانات المستخدم: `http://localhost:3000/privacy`
- مركز أمان المنصة: `http://localhost:3000/platform/security`
- طلب رفع خاص: `POST /v1/files/upload-intents`
- إكمال وفحص الملف: `POST /v1/files/{file_id}/complete`
- طلب تصدير: `POST /v1/me/data-export`
- تعطيل وإخفاء الحساب: `POST /v1/me/delete-account`
- مراجعات المخاطر: `GET /v1/platform/risk-assessments`
- Legal Hold: `GET/POST /v1/platform/legal-holds`
- لا ينتقل الملف من Quarantine إلى التخزين الخاص النهائي قبل نجاح الفحص، ولا يكشف عبور مكتب لمكتب وجود المورد أو مالكه.
- حذف الحساب يخفي غير الضروري ويلغي الجلسات، ولا يمحو التاريخ المالي والحجوزات الملزمة.
- إعداد Production يرفض التخزين الوهمي، غياب ماسح قابل للاستيراد، وكود Step-up التطويري.

## الاشتراكات والباقات

- اشتراك المكتب: `http://localhost:3000/office/subscription`
- مركز اشتراكات المنصة: `http://localhost:3000/platform/subscriptions`
- الاشتراك الحالي: `GET /v1/office/subscription`
- الخطط المتاحة للمكتب: `GET /v1/office/subscription-plans`
- طلب تغيير الخطة: `POST /v1/office/subscription/change-request`
- إدارة الخطط: `GET/POST /v1/platform/subscription-plans`
- تعيين اشتراك المكتب: `POST /v1/platform/offices/{office_id}/subscription`
- الفواتير: `GET /v1/platform/subscription-invoices`
- لا تعاد كتابة فترة مدفوعة عند تغير سعر الخطة، وانتهاء الاشتراك يوقف البيع الجديد فقط دون المساس بالحجوزات والحقوق القائمة.
- مهمة `subscriptions.process_due_subscriptions` تدير التجديد والاستحقاق وفترة السماح والانتهاء دوريًا.

## الاستمرارية والاختبار العملي

- مركز الاستمرارية: `http://localhost:3000/platform/continuity`
- الجاهزية: `GET /health/ready`
- أوامر الصيانة/التعافي/المصالحة: `POST /v1/platform/continuity/commands`
- النسخ والاستعادة: `scripts/backup_postgres.sh` و`scripts/restore_postgres.sh`
- Smoke وRollback: `scripts/smoke_release.sh` و`scripts/rollback_release.sh`
- اختبار UX الثابت: `cd apps/web && npm run test:ux-contract`
- اختبار المتصفح العملي يتطلب خادمي API/Web و`TRIP_ID`: `cd apps/web && npm run test:ux-browser`

الحزمة مكتملة وظيفيًا، لكن Production يبقى مشروطًا ببوابات البنية الخارجية الموضحة في `docs/FINAL_CLOSURE_STATUS.md`.


## نشر Demo مجاني على Render

الحزمة تتضمن `render.yaml` لإنشاء الواجهة والـAPI وPostgreSQL 18 وRedis تلقائيًا. راجع [دليل النشر العربي](DEPLOY_RENDER_AR.md).
