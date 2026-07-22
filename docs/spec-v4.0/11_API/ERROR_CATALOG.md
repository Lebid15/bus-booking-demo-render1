# مصفوفة أخطاء المجال وواجهات API

## نموذج الخطأ الموحد

```json
{
  "error": {
    "code": "SEAT_NOT_AVAILABLE",
    "message": "المقعد لم يعد متاحًا",
    "request_id": "uuid",
    "details": [{"field":"seat_id","reason":"already_assigned"}],
    "retryable": true
  }
}
```

- `message` مترجم ولا يكشف بيانات حساسة.
- `details` لا يعرض جنس أو هوية راكب آخر.
- الأخطاء الداخلية تسجل بالتفصيل خادميًا وتعود للعميل برسالة عامة.

| الرمز | HTTP | الرسالة | سبب الإطلاق | قابل للإعادة | الظهور |
|---|---:|---|---|---|---|
| `AUTH_REQUIRED` | 401 | يجب تسجيل الدخول | لا توجد جلسة/رمز صالح | لا | `public` |
| `AUTH_INVALID_CREDENTIALS` | 401 | بيانات الدخول غير صحيحة | فشل المصادقة | لا | `public` |
| `AUTH_MFA_REQUIRED` | 403 | يلزم تحقق إضافي | إجراء حساس أو حساب موظف | نعم | `public` |
| `AUTH_MFA_INVALID` | 403 | رمز التحقق غير صحيح | MFA فشل | نعم | `public` |
| `AUTH_SESSION_EXPIRED` | 401 | انتهت الجلسة | expires/revoked | نعم | `public` |
| `AUTH_ACCOUNT_SUSPENDED` | 403 | الحساب موقوف | حالة المستخدم | لا | `public` |
| `PERMISSION_DENIED` | 403 | ليس لديك صلاحية لهذا الإجراء | RBAC | لا | `public` |
| `TENANT_ACCESS_DENIED` | 403 | لا يمكن الوصول إلى بيانات هذا المكتب | عزل المستأجر | لا | `internal` |
| `RESOURCE_NOT_FOUND` | 404 | العنصر غير موجود | معرف غير صالح أو خارج النطاق | لا | `public` |
| `VALIDATION_ERROR` | 422 | تحقق من البيانات المدخلة | فشل schema/domain validation | نعم | `public` |
| `CONFLICT` | 409 | تعارضت العملية مع الحالة الحالية | Optimistic/state conflict | نعم | `public` |
| `STATE_TRANSITION_NOT_ALLOWED` | 409 | لا يمكن تنفيذ الإجراء في الحالة الحالية | انتقال غير موجود | لا | `public` |
| `VERSION_CONFLICT` | 409 | تم تعديل البيانات من مستخدم آخر | version mismatch | نعم | `public` |
| `IDEMPOTENCY_KEY_REQUIRED` | 400 | يلزم مفتاح منع التكرار | أمر مالي/حجز بلا header | نعم | `public` |
| `IDEMPOTENCY_KEY_REUSED` | 409 | أعيد استخدام المفتاح بطلب مختلف | request hash mismatch | لا | `public` |
| `RATE_LIMITED` | 429 | محاولات كثيرة، حاول لاحقًا | rate limit/risk | نعم | `public` |
| `TRIP_NOT_BOOKABLE` | 409 | الرحلة غير متاحة للحجز | حالة/وقت الرحلة | لا | `public` |
| `TRIP_NOT_READY` | 422 | بيانات الرحلة غير مكتملة | جدولة قبل اكتمالها | نعم | `office` |
| `TRIP_INVENTORY_INVALID` | 409 | مخطط مقاعد الرحلة غير صالح | trip_seats mismatch | لا | `office` |
| `TRIP_ALREADY_DEPARTED` | 409 | انطلقت الرحلة بالفعل | actual_departure_at | لا | `public` |
| `TRIP_DEPARTURE_BLOCKED` | 409 | لا يمكن تسجيل الانطلاق قبل معالجة التعارضات | manifest/seat/payment blockers | نعم | `office` |
| `TRIP_CANCEL_REASON_REQUIRED` | 422 | أدخل سبب إلغاء الرحلة | سبب فارغ | نعم | `office` |
| `TRIP_UNRESOLVED_CASES` | 409 | توجد حالات ركاب غير محسومة | دعم/boarding | نعم | `office` |
| `BOARDING_TOO_EARLY` | 409 | لم يحن وقت فتح الصعود | boarding_open_at | نعم | `office` |
| `BOARDING_NOT_OPEN` | 409 | الصعود غير مفتوح | حالة الرحلة | نعم | `public` |
| `URGENT_CASE_OPEN` | 409 | توجد حالة عاجلة تمنع إغلاق الصعود | P0/P1 | نعم | `office` |
| `SEAT_NOT_AVAILABLE` | 409 | المقعد لم يعد متاحًا | Hold/assignment قائم | نعم | `public` |
| `SEAT_HOLD_EXPIRED` | 409 | انتهت مهلة الاحتفاظ بالمقعد | expires_at | نعم | `public` |
| `SEAT_HOLD_NOT_OWNED` | 403 | الحجز المؤقت لا يخص هذه الجلسة | token/session mismatch | لا | `public` |
| `SEAT_GENDER_CONFLICT` | 409 | المقعد غير متاح وفق سياسة توزيع المقاعد | تجاور حجز مستقل مختلف الجنس | نعم | `public` |
| `SEAT_LAYOUT_MISMATCH` | 409 | المقعد لا ينتمي إلى مخطط الرحلة | layout mismatch | لا | `office` |
| `SEAT_REALLOCATION_REQUIRED` | 409 | يلزم اختيار مقعد بديل | تغيير البولمان/التوزيع | نعم | `public` |
| `PRICE_CHANGED` | 409 | تغير السعر، راجع السعر الجديد قبل المتابعة | snapshot/quote expired | نعم | `public` |
| `BOOKING_TRIP_NOT_BOOKABLE` | 409 | لا يمكن إنشاء حجز على هذه الرحلة | trip guard | لا | `public` |
| `BOOKING_DEADLINE_NOT_REACHED` | 409 | مهلة الدفع لم تنته بعد | expiry job early | لا | `internal` |
| `BOOKING_DEADLINE_EXPIRED` | 409 | انتهت مهلة الدفع | now > deadline | لا | `public` |
| `CANCELLATION_NOT_ALLOWED` | 409 | لا يسمح بالإلغاء وفق الشروط الحالية | policy snapshot | لا | `public` |
| `PASSENGER_ALREADY_BOARDED` | 409 | لا يمكن الإلغاء بعد تسجيل الصعود | boarding status | لا | `public` |
| `PASSENGER_DATA_INCOMPLETE` | 422 | أكمل بيانات جميع الركاب | passenger validation | نعم | `public` |
| `PASSENGER_GENDER_REQUIRED` | 422 | حدد جنس الراكب لاختيار المقعد | gender rule enabled | نعم | `public` |
| `NO_SHOW_NOT_ALLOWED` | 409 | لا يمكن تسجيل عدم الحضور الآن | trip/case guards | لا | `office` |
| `PAYMENT_REQUIRED` | 402 | يلزم إتمام الدفع أو تسجيله | booking payment rule | نعم | `public` |
| `PAYMENT_PROVIDER_UNAVAILABLE` | 503 | الدفع الإلكتروني غير متاح مؤقتًا | provider outage | نعم | `public` |
| `PAYMENT_AMOUNT_MISMATCH` | 409 | مبلغ الدفع لا يطابق المطلوب | amount/currency mismatch | لا | `public` |
| `PAYMENT_WEBHOOK_INVALID` | 400 | إشعار دفع غير صالح | signature/event invalid | لا | `internal` |
| `PAYMENT_ALREADY_SUCCEEDED` | 409 | تم تسجيل الدفع مسبقًا | intent succeeded | لا | `public` |
| `PAYMENT_STATE_CONFLICT` | 409 | حالة الدفع لا تسمح بهذا الإجراء | state machine | نعم | `public` |
| `PAYMENT_APPROVAL_REQUIRED` | 403 | يلزم اعتماد مالي إضافي | threshold/role | نعم | `office` |
| `PAYMENT_NOT_EXPIRED` | 409 | عملية الدفع لم تنته بعد | expires_at | لا | `internal` |
| `MANUAL_TRANSFER_DUPLICATE` | 409 | مرجع التحويل مستخدم سابقًا | unique ref/proof | لا | `public` |
| `MANUAL_TRANSFER_NOT_FOUND` | 422 | لم يتم العثور على التحويل في الحساب المستلم | actual receipt missing | نعم | `office` |
| `PAYMENT_REJECTION_REASON_REQUIRED` | 422 | أدخل سبب رفض التحويل | reason blank | نعم | `office` |
| `REFUND_AMOUNT_EXCEEDS_AVAILABLE` | 422 | المبلغ المطلوب أكبر من المتاح للاسترداد | paid-refunded-frozen | نعم | `public` |
| `REFUND_REQUIRED` | 409 | يجب إتمام الاسترداد قبل إغلاق الإلغاء | paid booking | نعم | `office` |
| `REFUND_NOT_COMPLETED` | 409 | الاسترداد لم يكتمل | refund state | نعم | `office` |
| `REFUND_ALREADY_APPROVED` | 409 | تم اعتماد طلب الاسترداد | state | لا | `public` |
| `REFUND_PROVIDER_UNAVAILABLE` | 503 | تعذر تنفيذ الاسترداد مؤقتًا | provider | نعم | `office` |
| `REFUND_RETRY_LIMIT` | 409 | تجاوزت العملية حد إعادة المحاولة | retry policy | لا | `office` |
| `REFUND_REJECTION_REASON_REQUIRED` | 422 | أدخل سبب رفض الاسترداد | reason blank | نعم | `office` |
| `CHARGEBACK_OPEN` | 409 | يوجد اعتراض دفع مفتوح على العملية | double compensation guard | لا | `office` |
| `DUAL_APPROVAL_REQUIRED` | 403 | يلزم اعتماد شخص آخر | maker-checker | نعم | `office` |
| `TICKET_INVALID` | 409 | التذكرة غير صالحة | revoked/expired/wrong booking | لا | `public` |
| `TICKET_ALREADY_USED` | 409 | استخدمت التذكرة سابقًا | used_at exists | لا | `office` |
| `TICKET_WRONG_TRIP` | 409 | التذكرة تخص رحلة أخرى | trip mismatch | لا | `office` |
| `TICKET_ISSUE_PRECONDITION` | 409 | لا يمكن إصدار التذكرة قبل تأكيد الحجز والمقعد | booking/seat guard | نعم | `internal` |
| `BOARDING_REVERSAL_NOT_ALLOWED` | 409 | لا يمكن عكس الصعود بعد الانطلاق | trip departed | لا | `office` |
| `DENIAL_REASON_REQUIRED` | 422 | أدخل سبب منع الصعود | reason blank | نعم | `office` |
| `OFFICE_NOT_ACTIVE` | 403 | المكتب غير مفعّل لنشر الرحلات | office status | لا | `office` |
| `OFFICE_NEW_BOOKINGS_DISABLED` | 403 | الحجوزات الجديدة متوقفة لهذا المكتب | restricted status | لا | `public` |
| `VERIFICATION_INCOMPLETE` | 422 | وثائق التحقق غير مكتملة | required docs | نعم | `office` |
| `VERIFICATION_REASON_REQUIRED` | 422 | يلزم تسجيل سبب القرار | decision reason | نعم | `platform` |
| `VERIFICATION_NOT_EXPIRED` | 409 | الوثائق ما زالت صالحة | expiry job | لا | `internal` |
| `PAYOUT_ACCOUNT_INVALID` | 409 | حساب التسوية غير معتمد | payout status | نعم | `platform` |
| `SETTLEMENT_PERIOD_OPEN` | 409 | فترة التسوية لم تغلق بعد | period end | لا | `platform` |
| `LEDGER_UNBALANCED` | 500 | تعذر إكمال العملية المالية | debit != credit | لا | `internal` |
| `SETTLEMENT_ITEMS_INVALID` | 409 | توجد عناصر تسوية غير متطابقة | reconciliation | نعم | `platform` |
| `SETTLEMENT_FROZEN` | 409 | جزء من المبلغ مجمد بسبب نزاع | freeze | نعم | `platform` |
| `SETTLEMENT_PAYMENT_UNCONFIRMED` | 409 | لم يثبت دفع التسوية | payment ref missing | نعم | `platform` |
| `SETTLEMENT_DISPUTE_OPEN` | 409 | يوجد اعتراض مفتوح على التسوية | dispute | لا | `platform` |
| `DISPUTE_EVIDENCE_REQUIRED` | 422 | أرفق الأدلة المطلوبة | evidence incomplete | نعم | `office` |
| `DISPUTE_DECISION_INCOMPLETE` | 422 | قرار النزاع غير مكتمل | code/reason/effect | نعم | `platform` |
| `DISPUTE_APPEAL_NOT_ALLOWED` | 409 | لا يمكن تقديم اعتراض جديد | window/used | لا | `public` |
| `DISPUTE_APPEAL_WINDOW_OPEN` | 409 | ما زالت مهلة الاعتراض مفتوحة | close early | لا | `internal` |
| `DUAL_REVIEW_REQUIRED` | 403 | يلزم مراجع مستقل | appeal reviewer same | نعم | `platform` |
| `POLICY_ACCEPTANCE_REQUIRED` | 428 | يجب الموافقة على الشروط قبل المتابعة | missing version acceptance | نعم | `public` |
| `POLICY_VERSION_EXPIRED` | 409 | إصدار الشروط لم يعد نافذًا | new flow uses old policy | نعم | `public` |
| `CONFIGURATION_OUT_OF_RANGE` | 422 | القيمة خارج الحدود التي تسمح بها المنصة | office config boundary | نعم | `office` |
| `LEGAL_HOLD_ACTIVE` | 409 | لا يمكن حذف أو إخفاء البيانات لوجود حجز قانوني | privacy delete | لا | `public` |
| `FILE_TYPE_NOT_ALLOWED` | 422 | نوع الملف غير مسموح | upload allowlist | نعم | `public` |
| `FILE_MALWARE_DETECTED` | 422 | تعذر قبول الملف | scan failed | لا | `public` |
| `SERVICE_DEGRADED` | 503 | الخدمة متاحة بصورة محدودة | dependency outage | نعم | `public` |
| `OFFLINE_SYNC_CONFLICT` | 409 | وجد تعارض أثناء مزامنة العمليات غير المتصلة | same passenger/ticket events | نعم | `office` |
| `RISK_MANUAL_REVIEW_REQUIRED` | 202 | العملية قيد المراجعة الأمنية | risk decision | لا | `public` |
| `RISK_BLOCKED` | 403 | تعذر تنفيذ العملية لأسباب أمنية | risk block | لا | `public` |
| `BOARDING_NOT_PROVEN` | 409 | لم يثبت صعود الراكب | حل منع الصعود بلا دليل | نعم | `platform` |
| `DISPUTE_OFFICE_NOT_RESPONSIBLE` | 409 | لا يمكن إحالة النزاع إلى هذا المكتب | مسؤولية مختلفة | نعم | `platform` |
| `DISPUTE_SLA_NOT_EXPIRED` | 409 | مهلة رد المكتب لم تنته بعد | تصعيد مبكر | لا | `internal` |
| `EVIDENCE_INSUFFICIENT` | 422 | الأدلة غير كافية لاتخاذ القرار | ملف ناقص | نعم | `platform` |
| `INCIDENT_NOT_RESOLVED` | 409 | الحادث لم يُحسم بعد | محاولة إغلاق رحلة متوقفة | نعم | `platform` |
| `PASSENGER_STATE_UNRESOLVED` | 409 | توجد حالة راكب غير محسومة | إكمال حجز قبل حسم الركاب | نعم | `internal` |
| `REFUND_CONFIRMATION_INVALID` | 409 | إثبات تنفيذ الاسترداد غير صالح | مرجع مزود/دليل غير صحيح | نعم | `platform` |
| `REFUND_REVIEW_INVALID` | 409 | لا يمكن بدء مراجعة الاسترداد بالحالة الحالية | انتقال غير صالح | نعم | `platform` |
| `REFUND_STATE_CONFLICT` | 409 | حالة الاسترداد لا تسمح بهذا الإجراء | تعارض حالة | نعم | `platform` |
| `SETTLEMENT_RETRY_BLOCKED` | 409 | لا يمكن إعادة محاولة التسوية قبل معالجة السبب | حساب/تجميد/مرجع | نعم | `platform` |
| `SETTLEMENT_STATE_CONFLICT` | 409 | حالة التسوية لا تسمح بهذا الإجراء | تعارض حالة | نعم | `platform` |
| `TICKET_NOT_EXPIRED` | 409 | التذكرة لم تنته صلاحيتها بعد | مهمة انتهاء مبكرة | لا | `internal` |
| `TRIP_ALREADY_COMPLETED` | 409 | أغلقت الرحلة بالفعل | إجراء بعد الإغلاق | لا | `public` |
| `TRIP_NOT_COMPLETED` | 409 | الرحلة لم تكتمل بعد | إكمال الحجز مبكرًا | لا | `internal` |
| `TRIP_NOT_DEPARTED` | 409 | الرحلة لم تنطلق بعد | وصول/توقف قبل الانطلاق | لا | `office` |
| `VERIFICATION_CONDITIONS_REQUIRED` | 422 | حدد شروط الاعتماد المؤقت وحدوده | اعتماد مشروط ناقص | نعم | `platform` |
| `VERIFICATION_EXTERNAL_UNAVAILABLE` | 503 | تعذر إكمال التحقق الخارجي مؤقتًا | مزود/جهة خارجية | نعم | `platform` |
| `VERIFICATION_REVIEWER_REQUIRED` | 422 | يجب تعيين مراجع للطلب | بدء مراجعة بلا مراجع | نعم | `platform` |
