# كتالوج آلات الحالات والانتقالات الكامل

> هذه الوثيقة معيارية. أي انتقال غير مذكور مرفوض افتراضيًا بـ`STATE_TRANSITION_NOT_ALLOWED`.

## قواعد مشتركة

- كل انتقال ينفذ داخل معاملة قاعدة بيانات واحدة ويكتب `audit_logs` و`outbox_events` عند وجود أثر خارجي.
- يستخدم `version` للتفاؤل، وأقفال صفوف للمقاعد والمال.
- `Actor` يعني الدور المسموح، وليس قيمة يرسلها العميل.
- Side effects لا تنفذ قبل commit؛ الأحداث الخارجية تخرج من Transactional Outbox.
- التصحيح بعد الحالة النهائية يكون بحدث عكسي/Adjustment، لا بإعادة الحالة بصمت.

# booking

**الكيان:** `bookings` — **البداية:** `draft` — **النهايات:** `cancelled`, `completed`, `no_show`

## الحالات

- `draft`: مسودة لم تثبت المقاعد نهائيًا
- `awaiting_payment`: حجز مقاعد مؤكد بمهلة دفع
- `confirmed`: مؤكد ومستوفٍ لشروط الإصدار
- `cancellation_pending`: إلغاء يحتاج معالجة مالية/تشغيلية
- `cancelled`: ملغى نهائيًا
- `completed`: نفذت الرحلة للركاب
- `no_show`: لم يحضر وفق الشروط
- `denied_boarding_review`: منع صعود قيد التحقيق

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `create_draft` | `∅` | `draft` | `customer`, `office_agent` | بيانات رحلة صالحة وعدد ركاب ضمن الحد | إنشاء PNR أولي غير قابل للاستخدام كتذكرة؛ Audit | `BOOKING_TRIP_NOT_BOOKABLE` |
| `reserve_seats` | `draft` | `awaiting_payment` | `customer`, `office_agent` | كل المقاعد متاحة؛ قواعد الجنس صحيحة؛ Hold ملك الجلسة؛ السعر ما زال صالحًا | تثبيت seat_assignments؛ حفظ snapshots؛ تحديد مهلة الدفع؛ commission expected؛ outbox | `SEAT_NOT_AVAILABLE|SEAT_GENDER_CONFLICT|PRICE_CHANGED` |
| `confirm_no_prepayment` | `awaiting_payment` | `confirmed` | `system`, `office_finance` | طريقة الدفع تسمح بالتأكيد غير المدفوع أو الدفع سجل بنجاح | إصدار تذاكر؛ إشعار؛ booking.confirmed_at | `PAYMENT_REQUIRED` |
| `payment_succeeded` | `awaiting_payment` | `confirmed` | `system`, `office_finance` | مجموع المدفوع >= المطلوب؛ المقعد ما زال مملوكًا للحجز | إصدار تذاكر؛ ledger event؛ إشعار | `PAYMENT_AMOUNT_MISMATCH` |
| `expire_payment_deadline` | `awaiting_payment` | `cancelled` | `system` | الوقت تجاوز المهلة؛ لا دفع صالح ضمن المهلة؛ لا Legal Hold | تحرير المقاعد؛ إبطال intents؛ commission reversed؛ إشعار | `BOOKING_DEADLINE_NOT_REACHED` |
| `request_cancel` | `awaiting_payment|confirmed` | `cancellation_pending` | `customer`, `office_agent`, `platform_support` | السياسة تسمح أو إلغاء مكتب/حادث؛ لا صعود فعلي | حساب quote؛ تجميد تعديلات؛ إنشاء refund عند الحاجة | `CANCELLATION_NOT_ALLOWED|PASSENGER_ALREADY_BOARDED` |
| `cancel_without_refund` | `cancellation_pending` | `cancelled` | `system`, `office_manager` | لا مبلغ مستحق أو سياسة لا استرداد؛ اعتماد عند اللزوم | تحرير المقاعد؛ إبطال tickets؛ commission status وفق السياسة | `REFUND_REQUIRED` |
| `cancel_after_refund` | `cancellation_pending` | `cancelled` | `system` | الاسترداد المطلوب succeeded أو لا يوجد دفع خارجي | تحرير المقاعد؛ إبطال tickets؛ تعديل العمولة | `REFUND_NOT_COMPLETED` |
| `open_denied_boarding` | `confirmed` | `denied_boarding_review` | `support`, `system` | حالة P1/P0 موثقة قبل/عند الانطلاق | تجميد إعادة بيع المقعد؛ فتح support case | `TRIP_ALREADY_COMPLETED` |
| `resolve_denied_boarding_in_favor_customer` | `denied_boarding_review` | `cancellation_pending` | `platform_support` | ثبت إخلال المكتب أو تعذر الصعود | استرداد/بديل وتعويض؛ مخالفة مكتب | `EVIDENCE_INSUFFICIENT` |
| `resolve_denied_boarding_boarded` | `denied_boarding_review` | `confirmed` | `platform_support` | ثبت صعود الراكب أو حل المشكلة | رفع التجميد وتحديث الحالة | `BOARDING_NOT_PROVEN` |
| `mark_completed` | `confirmed` | `completed` | `system` | الرحلة completed وكل الركاب boarded أو معالجون؛ لا حالة denied مفتوحة | commission earned؛ أهلية التسوية | `TRIP_NOT_COMPLETED|PASSENGER_STATE_UNRESOLVED` |
| `mark_no_show` | `confirmed` | `no_show` | `system`, `office_boarding` | انطلاق فعلي؛ لا boarded؛ لا P0/P1/denied؛ النداء النهائي تم | تطبيق السياسة؛ commission earned/recalculated؛ Audit | `NO_SHOW_NOT_ALLOWED` |

# payment_intent

**الكيان:** `payment_intents` — **البداية:** `created` — **النهايات:** `succeeded`, `failed`, `cancelled`, `expired`

## الحالات

- `created`: أنشئت النية
- `requires_action`: ينتظر إجراء الزبون
- `pending_verification`: تحويل/نتيجة غير محسومة
- `succeeded`: نجاح نهائي
- `failed`: فشل نهائي
- `cancelled`: ألغيت
- `expired`: انتهت

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `start_electronic` | `created` | `requires_action` | `system` | مزود فعال؛ مبلغ/عملة مطابقان للحجز | إنشاء جلسة مزود دون تخزين بطاقة | `PAYMENT_PROVIDER_UNAVAILABLE` |
| `submit_manual` | `created` | `pending_verification` | `customer`, `office_agent` | مرجع تحويل فريد؛ المبلغ صحيح | حفظ proof hash؛ تنبيه المالية | `MANUAL_TRANSFER_DUPLICATE` |
| `record_office_cash` | `created` | `succeeded` | `office_finance` | صلاحية؛ إيصال؛ ضمن حدود الفرع | transaction + ledger + audit | `PAYMENT_APPROVAL_REQUIRED` |
| `provider_success` | `requires_action|pending_verification` | `succeeded` | `system` | Webhook موقّع؛ provider_event_id فريد؛ amount/currency مطابق | transaction؛ تحديث booking paid_amount؛ ledger؛ outbox | `PAYMENT_WEBHOOK_INVALID|PAYMENT_AMOUNT_MISMATCH` |
| `verify_manual` | `pending_verification` | `succeeded` | `office_finance` | وصول فعلي؛ reviewer غير صاحب العملية عند تجاوز الحد | transaction occurred_at=وقت التحويل؛ ledger | `MANUAL_TRANSFER_NOT_FOUND` |
| `reject_manual` | `pending_verification` | `failed` | `office_finance` | سبب موثق | إشعار؛ Audit | `PAYMENT_REJECTION_REASON_REQUIRED` |
| `provider_failed` | `requires_action` | `failed` | `system` | حدث موثق نهائي | إتاحة إعادة المحاولة بمفتاح جديد | `PAYMENT_STATE_CONFLICT` |
| `cancel` | `created|requires_action|pending_verification` | `cancelled` | `customer`, `system`, `office_finance` | لا transaction ناجحة | إبطال الجلسة الخارجية عند الإمكان | `PAYMENT_ALREADY_SUCCEEDED` |
| `expire` | `created|requires_action` | `expired` | `system` | تجاوز expires_at | لا أثر على حركة ناجحة متأخرة؛ تذهب للمصالحة | `PAYMENT_NOT_EXPIRED` |

# trip

**الكيان:** `trips` — **البداية:** `draft` — **النهايات:** `completed`, `cancelled`

## الحالات

- `draft`: مسودة
- `scheduled`: مجدولة داخليًا
- `published`: منشورة للعرض
- `booking_open`: مفتوحة للحجز
- `boarding_open`: فتح الصعود
- `boarding_closed`: أغلق الصعود
- `departed`: انطلقت
- `arrived`: وصلت
- `completed`: مغلقة تشغيليًا
- `cancelled`: ملغاة
- `interrupted`: توقفت بعد الانطلاق

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `schedule` | `draft` | `scheduled` | `office_manager` | مركبة/مسار/سعر/سياسة/وثائق صالحة | إنشاء trip_seats من layout snapshot | `TRIP_NOT_READY` |
| `publish` | `scheduled` | `published` | `office_manager` | المكتب active والرحلة ضمن نطاقه | ظهور عام دون فتح البيع قبل booking_open_at | `OFFICE_NOT_ACTIVE` |
| `open_booking` | `published` | `booking_open` | `system`, `office_manager` | الوقت مناسب؛ مخزون المقاعد موجود | إتاحة البحث والحجز | `TRIP_INVENTORY_INVALID` |
| `open_boarding` | `booking_open` | `boarding_open` | `system`, `office_boarding` | وصل boarding_open_at؛ manifest draft موجود | تجميد تعديلات حساسة؛ إشعار موظفي الصعود | `BOARDING_TOO_EARLY` |
| `close_boarding` | `boarding_open` | `boarding_closed` | `office_boarding`, `system` | النداء النهائي؛ معالجة الحالات العاجلة | manifest boarding_closed؛ منع حجز جديد | `URGENT_CASE_OPEN` |
| `depart` | `boarding_closed` | `departed` | `office_manager` | لا ازدواج مقاعد؛ مركبة وسائق فعليان؛ manifest متوازن | قفل manifest النهائي؛ actual_departure_at | `TRIP_DEPARTURE_BLOCKED` |
| `arrive` | `departed` | `arrived` | `office_manager` | وقت وصول فعلي | actual_arrival_at؛ فتح نافذة الشكاوى | `TRIP_NOT_DEPARTED` |
| `complete` | `arrived` | `completed` | `system`, `office_manager` | انتهاء نافذة التصحيح القصيرة؛ حالات الركاب محسومة | إغلاق تشغيلي؛ إطلاق أحداث مالية | `TRIP_UNRESOLVED_CASES` |
| `cancel_before_departure` | `scheduled|published|booking_open|boarding_open|boarding_closed` | `cancelled` | `office_manager`, `platform_ops` | سبب وتصنيف؛ خطة الركاب | إبطال البيع؛ إنشاء بدائل/استردادات؛ تجميد التسوية | `TRIP_CANCEL_REASON_REQUIRED` |
| `interrupt` | `departed` | `interrupted` | `office_manager`, `platform_ops` | حادث/تعذر استمرار | فتح incident؛ تجميد الأموال المتأثرة | `TRIP_NOT_DEPARTED` |
| `resolve_interrupted_as_completed` | `interrupted` | `completed` | `platform_ops` | تم نقل الركاب أو إكمال الخدمة وحقوقهم | تسويات معدلة؛ إغلاق incident | `INCIDENT_NOT_RESOLVED` |
| `resolve_interrupted_as_cancelled` | `interrupted` | `cancelled` | `platform_ops` | لم تنفذ الخدمة بصورة مقبولة | استرداد/تعويض | `INCIDENT_NOT_RESOLVED` |

# boarding

**الكيان:** `booking_passengers.boarding_status` — **البداية:** `not_arrived` — **النهايات:** `boarded`, `denied`, `no_show`

## الحالات

- `not_arrived`: لم يصل
- `arrived`: حضر
- `verified`: تحقق
- `boarded`: صعد
- `boarded_reversed`: عكس قبل الانطلاق
- `denied`: منع صعود
- `no_show`: لم يحضر

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `mark_arrived` | `not_arrived` | `arrived` | `office_boarding` | الرحلة boarding_open؛ الراكب مؤكد | boarding_event | `BOARDING_NOT_OPEN` |
| `verify` | `arrived|not_arrived` | `verified` | `office_boarding` | تذكرة فعالة أو تحقق يدوي موثق؛ شرط الدفع مستوفى | event + audit manual if applicable | `TICKET_INVALID|PAYMENT_REQUIRED` |
| `board` | `verified` | `boarded` | `office_boarding` | عملية ذرية؛ لا boarded سابق؛ الرحلة لم تنطلق | ticket used_at؛ event | `TICKET_ALREADY_USED` |
| `reverse_before_departure` | `boarded` | `boarded_reversed` | `office_boarding` | trip not departed؛ سبب | ticket يعود active بإصدار نفسه أو إجراء مضبوط | `BOARDING_REVERSAL_NOT_ALLOWED` |
| `reboard` | `boarded_reversed` | `boarded` | `office_boarding` | trip not departed | event جديد idempotent | `TRIP_ALREADY_DEPARTED` |
| `deny` | `arrived|verified` | `denied` | `office_boarding`, `platform_support` | سبب موثق؛ فتح حالة دعم عند نزاع | booking denied_boarding_review عند الحاجة | `DENIAL_REASON_REQUIRED` |
| `mark_no_show` | `not_arrived|arrived` | `no_show` | `system`, `office_boarding` | trip departed؛ arrived لا يسمح إلا بعد تحقق عدم وجود الراكب/حالة دعم | تطبيق سياسة no-show | `NO_SHOW_NOT_ALLOWED` |

# refund

**الكيان:** `refunds` — **البداية:** `requested` — **النهايات:** `succeeded`, `rejected`, `cancelled`

## الحالات

- `requested`: طلب
- `under_review`: مراجعة
- `approved`: معتمد
- `processing`: قيد التنفيذ
- `succeeded`: نجح
- `failed`: فشل قابل للمحاولة
- `rejected`: مرفوض
- `cancelled`: ملغى

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `submit` | `∅` | `requested` | `customer`, `office_agent`, `system` | مبلغ متاح للاسترداد؛ لا duplicate | حجز المبلغ المختلف عليه | `REFUND_AMOUNT_EXCEEDS_AVAILABLE` |
| `review` | `requested` | `under_review` | `office_finance`, `platform_finance` | أدلة وسياسة snapshot | حساب quote | `REFUND_REVIEW_INVALID` |
| `approve` | `under_review` | `approved` | `office_finance`, `platform_finance` | approved_by مختلف؛ لا chargeback تعويض مكرر | ledger pending/refund liability | `DUAL_APPROVAL_REQUIRED|CHARGEBACK_OPEN` |
| `reject` | `under_review` | `rejected` | `office_finance`, `platform_finance` | سبب واضح وقابل للاعتراض | رفع الحجز المالي؛ إشعار | `REFUND_REJECTION_REASON_REQUIRED` |
| `process` | `approved` | `processing` | `system` | وسيلة أصلية متاحة أو مسار استثنائي معتمد | نداء مزود/idempotency | `REFUND_PROVIDER_UNAVAILABLE` |
| `succeed` | `processing` | `succeeded` | `system` | تأكيد مزود أو إثبات دفع يدوي | ledger reversal/expense؛ booking totals؛ commission adjust | `REFUND_CONFIRMATION_INVALID` |
| `fail` | `processing` | `failed` | `system` | فشل مزود قابل للتوثيق | إعادة محاولة أو تصعيد | `REFUND_STATE_CONFLICT` |
| `retry` | `failed` | `processing` | `system`, `platform_finance` | ضمن حد المحاولات | محاولة idempotent جديدة | `REFUND_RETRY_LIMIT` |
| `cancel_request` | `requested` | `cancelled` | `customer`, `platform_finance` | لم يعتمد ولم ينفذ | رفع الحجز | `REFUND_ALREADY_APPROVED` |

# dispute

**الكيان:** `disputes` — **البداية:** `open` — **النهايات:** `closed`

## الحالات

- `open`: مفتوح
- `awaiting_office`: ينتظر المكتب
- `under_review`: مراجعة
- `decided`: قرار أولي
- `appealed`: اعتراض واحد
- `closed`: مغلق

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `assign_office` | `open` | `awaiting_office` | `platform_support` | المكتب مسؤول عن الرد | SLA due | `DISPUTE_OFFICE_NOT_RESPONSIBLE` |
| `office_respond` | `awaiting_office` | `under_review` | `office_manager` | أدلة مكتملة أو انتهاء المهلة | evidence bundle locked | `DISPUTE_EVIDENCE_REQUIRED` |
| `escalate_no_response` | `awaiting_office` | `under_review` | `system` | انتهاء SLA | مخالفة مكتب؛ قرار بالأدلة المتاحة | `DISPUTE_SLA_NOT_EXPIRED` |
| `decide` | `under_review` | `decided` | `platform_support`, `platform_finance` | decision code + reasoning + financial effect | refund/adjustment tasks | `DISPUTE_DECISION_INCOMPLETE` |
| `appeal` | `decided` | `appealed` | `customer`, `office_manager` | ضمن 7 أيام؛ لم يستخدم الاعتراض | assign independent reviewer | `DISPUTE_APPEAL_NOT_ALLOWED` |
| `decide_appeal` | `appealed` | `closed` | `platform_support` | مراجع مختلف؛ قرار نهائي | final adjustments | `DUAL_REVIEW_REQUIRED` |
| `close_no_appeal` | `decided` | `closed` | `system` | انتهاء مهلة الاعتراض وتنفيذ القرار | رفع freezes غير اللازمة | `DISPUTE_APPEAL_WINDOW_OPEN` |

# settlement

**الكيان:** `settlements` — **البداية:** `draft` — **النهايات:** `paid`, `closed`

## الحالات

- `draft`: مسودة
- `calculated`: محسوبة
- `under_review`: مراجعة
- `approved`: معتمدة
- `processing`: قيد الدفع
- `paid`: مدفوعة
- `failed`: فشلت
- `closed`: مغلقة

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `calculate` | `draft` | `calculated` | `system`, `platform_finance` | الفترة مغلقة؛ ledger reconciled | إنشاء immutable items | `SETTLEMENT_PERIOD_OPEN|LEDGER_UNBALANCED` |
| `submit_review` | `calculated` | `under_review` | `platform_finance` | لا عناصر غير مفسرة | قفل التعديل المباشر | `SETTLEMENT_ITEMS_INVALID` |
| `approve` | `under_review` | `approved` | `platform_finance_approver` | approver != creator؛ حساب payout active | ledger payable | `DUAL_APPROVAL_REQUIRED|PAYOUT_ACCOUNT_INVALID` |
| `process` | `approved` | `processing` | `system`, `platform_finance` | لا freeze يتجاوز المتاح | إرسال دفع أو اعتماد مقاصة | `SETTLEMENT_FROZEN` |
| `mark_paid` | `processing` | `paid` | `system`, `platform_finance` | مرجع دفع مثبت | ledger clear payable؛ commissions paid | `SETTLEMENT_PAYMENT_UNCONFIRMED` |
| `fail` | `processing` | `failed` | `system` | فشل موثق | إعادة للمراجعة دون تعديل items | `SETTLEMENT_STATE_CONFLICT` |
| `retry` | `failed` | `processing` | `platform_finance` | حساب فعال وتصحيح السبب | محاولة جديدة | `SETTLEMENT_RETRY_BLOCKED` |
| `close` | `paid` | `closed` | `system` | لا اعتراض مفتوح على الدفعة | أرشفة | `SETTLEMENT_DISPUTE_OPEN` |

# office_verification

**الكيان:** `verification_cases` — **البداية:** `draft` — **النهايات:** `approved`, `rejected`, `expired`

## الحالات

- `draft`: مسودة
- `submitted`: مرسل
- `under_review`: مراجعة
- `info_required`: معلومات إضافية
- `external_verification`: تحقق خارجي
- `conditional`: اعتماد مشروط
- `approved`: معتمد
- `rejected`: مرفوض
- `expired`: منتهي

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `submit` | `draft` | `submitted` | `office_owner` | الحقول والوثائق الدنيا | قفل النسخة | `VERIFICATION_INCOMPLETE` |
| `start_review` | `submitted` | `under_review` | `platform_compliance` | مراجع معين | SLA | `VERIFICATION_REVIEWER_REQUIRED` |
| `request_info` | `under_review` | `info_required` | `platform_compliance` | قائمة نواقص | إشعار | `VERIFICATION_REASON_REQUIRED` |
| `resubmit` | `info_required` | `submitted` | `office_owner` | النواقص مرفوعة | version++ | `VERIFICATION_INCOMPLETE` |
| `external_check` | `under_review` | `external_verification` | `platform_compliance` | حاجة تحقق جهة خارجية | تعليق القرار | `VERIFICATION_EXTERNAL_UNAVAILABLE` |
| `conditional_approve` | `under_review|external_verification` | `conditional` | `platform_compliance_approver` | حدود وشروط وانتهاء محدد | office conditional limits | `VERIFICATION_CONDITIONS_REQUIRED` |
| `approve` | `under_review|external_verification|conditional` | `approved` | `platform_compliance_approver` | كل الحرج verified؛ reviewer != approver للحالات المعززة | office active عند اكتمال العقد | `DUAL_APPROVAL_REQUIRED` |
| `reject` | `under_review|external_verification` | `rejected` | `platform_compliance_approver` | سبب قابل للإبلاغ | حق إعادة التقديم/اعتراض | `VERIFICATION_REASON_REQUIRED` |
| `expire` | `approved|conditional` | `expired` | `system` | وثيقة حرجة انتهت دون تجديد | تقييد تعيينات جديدة؛ لا إلغاء صامت للقائم | `VERIFICATION_NOT_EXPIRED` |

# ticket

**الكيان:** `tickets` — **البداية:** `active` — **النهايات:** `used`, `expired`

## الحالات

- `active`: صالح
- `revoked`: مبطل
- `used`: مستخدم
- `expired`: منتهي

## الانتقالات

| الأمر | من | إلى | المنفذون | Guards | الآثار الذرية/اللاحقة | أخطاء المجال |
|---|---|---|---|---|---|---|
| `issue` | `∅` | `active` | `system` | booking confirmed؛ seat active؛ no active ticket | QR signed; version++ | `TICKET_ISSUE_PRECONDITION` |
| `revoke_for_change` | `active` | `revoked` | `system` | تغيير مقعد/راكب/رحلة أو إلغاء | إصدار جديد إن بقي الحجز صالحًا | `TICKET_ALREADY_USED` |
| `use` | `active` | `used` | `office_boarding` | مسح ذري؛ رحلة صحيحة؛ لم يستخدم | boarding event | `TICKET_ALREADY_USED|TICKET_WRONG_TRIP` |
| `expire` | `active|revoked` | `expired` | `system` | انتهاء الرحلة/مدة الاحتفاظ التشغيلي | لا حذف | `TICKET_NOT_EXPIRED` |
