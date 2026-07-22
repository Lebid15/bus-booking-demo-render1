# مواصفة أحداث دفتر الأستاذ المالي

> دفتر مزدوج القيد، append-only. لا تعدّل القيود المنشورة؛ أي تصحيح بقيد عكسي مرتبط بـ`reversal_of_id`.

## مبادئ الاعتراف

1. الدفع ليس إيرادًا فورًا؛ الدفع الإلكتروني قبل الرحلة يمثل `CUSTOMER_FUNDS`.
2. العمولة تُكتسب عند تنفيذ الخدمة أو No-show غير قابل للاسترداد وفق Snapshot.
3. الأموال المدفوعة مباشرة للمكتب لا تدخل بنك المنصة؛ تسجل عمولة مستحقة على المكتب عند اكتسابها.
4. يجمد فقط المبلغ المتنازع عليه.
5. الاسترداد لا يُنفذ مرتين مع Chargeback/تعويض لنفس الأساس.
6. كل حدث تجاري يملك `event_type + event_id` فريدين، مما يجعل النشر idempotent.

## دليل الحسابات الأدنى

| الرمز | النوع | الوصف |
|---|---|---|
| `1000_BANK` | `asset` | رصيد المنصة لدى البنك/المحفظة |
| `1010_PSP_RECEIVABLE` | `asset` | مبالغ مستحقة من مزود الدفع |
| `1020_OFFICE_COMMISSION_RECEIVABLE` | `asset` | عمولات مستحقة على مكاتب استلمت المال مباشرة |
| `1030_OTHER_RECEIVABLE` | `asset` | ذمم أخرى موثقة |
| `2000_CUSTOMER_FUNDS` | `liability` | أموال زبائن محتجزة قبل استحقاق الخدمة |
| `2010_OFFICE_PAYABLE` | `liability` | صافي مستحق للمكتب |
| `2020_REFUND_PAYABLE` | `liability` | استردادات معتمدة قيد التنفيذ |
| `2030_RESERVE_HELD` | `liability` | احتياطي محجوز من مستحقات المكتب |
| `1040_CHARGEBACK_RECEIVABLE` | `asset` | مبلغ سحبه المزود مؤقتًا وقيد المطالبة/الدفاع |
| `2050_PROVIDER_FEES_PAYABLE` | `liability` | رسوم مزود لم تسحب بعد |
| `4000_COMMISSION_REVENUE` | `revenue` | عمولة المنصة المكتسبة |
| `4010_SUBSCRIPTION_REVENUE` | `revenue` | إيراد اشتراك المكتب |
| `4090_COMMISSION_REVERSAL` | `contra` | عكس/تخفيض إيراد عمولة |
| `5000_PAYMENT_PROVIDER_FEES` | `expense` | رسوم بوابة الدفع |
| `5010_CUSTOMER_COMPENSATION` | `expense` | تعويض تتحمله المنصة |
| `5020_FRAUD_LOSS` | `expense` | خسارة احتيال معتمدة |
| `5030_BAD_DEBT` | `expense` | ذمة مكتب غير قابلة للتحصيل |

## كتالوج الأحداث والقيود

### `ELECTRONIC_PAYMENT_CAPTURED`

- **متى:** تأكيد مزود الدفع قبض المبلغ من الزبون
- **المصدر:** `payment_transaction`
- **الشروط:** event id فريد؛ amount/currency مطابقان للنية؛ الحجز غير مسترد بالكامل

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1010_PSP_RECEIVABLE` | `gross_amount` |
| `C` | `2000_CUSTOMER_FUNDS` | `gross_amount` |
- **الآثار:** booking.paid_amount += gross؛ payment_intent=succeeded
- **العكس:** `ELECTRONIC_PAYMENT_REVERSED`

### `PSP_FEE_RECOGNIZED`

- **متى:** استلام كشف/حدث رسوم المزود
- **المصدر:** `provider_fee_event`
- **الشروط:** fee>=0؛ مرجع مزود فريد

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `5000_PAYMENT_PROVIDER_FEES` | `fee_amount` |
| `C` | `1010_PSP_RECEIVABLE` | `fee_amount` |
- **الآثار:** ربط الرسوم بالحركة
- **العكس:** `PSP_FEE_REVERSED`

### `PSP_FUNDS_SETTLED`

- **متى:** تحويل المزود صافي الأموال إلى حساب المنصة
- **المصدر:** `provider_settlement`
- **الشروط:** مطابقة batch؛ لا فرق غير مفسر

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1000_BANK` | `settled_amount` |
| `C` | `1010_PSP_RECEIVABLE` | `settled_amount` |
- **الآثار:** إغلاق batch أو تسجيل فرق للمصالحة
- **العكس:** `PSP_SETTLEMENT_REVERSED`

### `SERVICE_COMPLETED_ELECTRONIC`

- **متى:** الحجز مؤهل ماليًا بعد اكتمال الرحلة/No-show حسب السياسة
- **المصدر:** `booking_completion`
- **الشروط:** commission snapshot ثابت؛ لا refund pending على المبلغ نفسه
- **معادلة:** `recognized_gross = office_net + commission_amount`

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2000_CUSTOMER_FUNDS` | `recognized_gross` |
| `C` | `2010_OFFICE_PAYABLE` | `office_net` |
| `C` | `4000_COMMISSION_REVENUE` | `commission_amount` |
- **الآثار:** commission=earned؛ booking eligible for settlement
- **العكس:** `SERVICE_RECOGNITION_REVERSED`

### `COMMISSION_EARNED_DIRECT`

- **متى:** اكتمال خدمة حجز دُفع مباشرة للمكتب
- **المصدر:** `booking_completion`
- **الشروط:** الدفع المباشر verified؛ commission snapshot ثابت

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1020_OFFICE_COMMISSION_RECEIVABLE` | `commission_amount` |
| `C` | `4000_COMMISSION_REVENUE` | `commission_amount` |
- **الآثار:** commission=earned؛ إدراجها في المقاصة/فاتورة المكتب
- **العكس:** `COMMISSION_REVERSED_DIRECT`

### `DIRECT_COMMISSION_NETTED`

- **متى:** خصم عمولة مستحقة على المكتب من مستحقاته الإلكترونية
- **المصدر:** `settlement_item`
- **الشروط:** نفس المكتب والعملة؛ receivable متاح

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2010_OFFICE_PAYABLE` | `netted_amount` |
| `C` | `1020_OFFICE_COMMISSION_RECEIVABLE` | `netted_amount` |
- **الآثار:** إضافة عنصر مقاصة للتسوية
- **العكس:** `DIRECT_COMMISSION_NETTING_REVERSED`

### `OFFICE_COMMISSION_PAID`

- **متى:** سداد المكتب عمولة مباشرة للمنصة
- **المصدر:** `office_payment`
- **الشروط:** مرجع قبض مثبت

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1000_BANK` | `amount` |
| `C` | `1020_OFFICE_COMMISSION_RECEIVABLE` | `amount` |
- **الآثار:** خفض ذمة المكتب
- **العكس:** `OFFICE_COMMISSION_PAYMENT_REVERSED`

### `REFUND_APPROVED_PRE_SERVICE`

- **متى:** اعتماد استرداد قبل استحقاق الإيراد
- **المصدر:** `refund`
- **الشروط:** المبلغ ضمن CUSTOMER_FUNDS؛ لا chargeback مزدوج

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2000_CUSTOMER_FUNDS` | `refund_amount` |
| `C` | `2020_REFUND_PAYABLE` | `refund_amount` |
- **الآثار:** حجز المبلغ للاسترداد
- **العكس:** `REFUND_APPROVAL_CANCELLED`

### `REFUND_EXECUTED`

- **متى:** تأكيد خروج الاسترداد إلى وسيلة الدفع الأصلية
- **المصدر:** `refund_transaction`
- **الشروط:** refund approved؛ provider reference فريد
- **حسم الحساب:** استخدم 1010 إن خصم المزود قبل التسوية، وإلا 1000

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2020_REFUND_PAYABLE` | `refund_amount` |
| `C` | `1000_BANK_OR_PSP` | `refund_amount` |
- **الآثار:** refund=succeeded؛ booking.refunded_amount += amount
- **العكس:** `REFUND_EXECUTION_REVERSED`

### `REFUND_AFTER_RECOGNITION_ELECTRONIC`

- **متى:** استرداد بعد اكتساب عمولة ومبلغ مكتب
- **المصدر:** `refund_approval`
- **الشروط:** تحديد من يتحمل الجزء وفق policy/causality
- **معادلة:** `refund_amount = office_share + platform_share`

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2010_OFFICE_PAYABLE` | `office_share` |
| `D` | `4090_COMMISSION_REVERSAL` | `platform_share` |
| `C` | `2020_REFUND_PAYABLE` | `refund_amount` |
- **الآثار:** commission adjusted؛ تخفيض صافي المكتب
- **العكس:** `POST_RECOGNITION_REFUND_CANCELLED`

### `REFUND_AFTER_RECOGNITION_DIRECT`

- **متى:** إلغاء/استرداد حجز كان المال عند المكتب
- **المصدر:** `refund_approval`
- **الشروط:** المكتب مسؤول عن رد العميل أو إثبات التنفيذ

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `4090_COMMISSION_REVERSAL` | `commission_reversal` |
| `C` | `1020_OFFICE_COMMISSION_RECEIVABLE` | `commission_reversal` |
- **الآثار:** تخفيض عمولة المكتب؛ الاسترداد نفسه خارج حساب المنصة ويثبت تشغيليًا
- **العكس:** `DIRECT_REFUND_REVERSAL_CANCELLED`

### `RESERVE_WITHHELD`

- **متى:** حجز احتياطي مخاطر من مستحق مكتب
- **المصدر:** `reserve_rule`
- **الشروط:** حد معتمد؛ المبلغ <= office payable

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2010_OFFICE_PAYABLE` | `reserve_amount` |
| `C` | `2030_RESERVE_HELD` | `reserve_amount` |
- **الآثار:** settlement reserve item
- **العكس:** `RESERVE_RELEASED`

### `RESERVE_RELEASED`

- **متى:** انتهاء سبب الاحتياطي
- **المصدر:** `reserve_release`
- **الشروط:** لا نزاع/تعرض قائم

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2030_RESERVE_HELD` | `reserve_amount` |
| `C` | `2010_OFFICE_PAYABLE` | `reserve_amount` |
- **الآثار:** إتاحة المبلغ للتسوية
- **العكس:** `RESERVE_REWITHHELD`

### `OFFICE_PAYOUT_SENT`

- **متى:** إثبات دفع التسوية للمكتب
- **المصدر:** `settlement_payment`
- **الشروط:** settlement approved؛ payout account active؛ مرجع فريد

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2010_OFFICE_PAYABLE` | `payout_amount` |
| `C` | `1000_BANK` | `payout_amount` |
- **الآثار:** settlement=paid؛ commissions=paid
- **العكس:** `OFFICE_PAYOUT_REVERSED`

### `CHARGEBACK_OPENED`

- **متى:** إشعار اعتراض بنكي
- **المصدر:** `chargeback`
- **الشروط:** provider case فريد
- **حسم الحساب:** بحسب وقت سحب المزود للمبلغ

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1040_CHARGEBACK_RECEIVABLE` | `disputed_amount` |
| `C` | `1010_PSP_RECEIVABLE_OR_BANK` | `disputed_amount` |
- **الآثار:** تجميد المبلغ المتأثر فقط
- **العكس:** `CHARGEBACK_WON`

### `CHARGEBACK_WON`

- **متى:** إغلاق الاعتراض لصالح المنصة
- **المصدر:** `chargeback_decision`
- **الشروط:** case status won

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1010_PSP_RECEIVABLE_OR_BANK` | `recovered_amount` |
| `C` | `1040_CHARGEBACK_RECEIVABLE` | `recovered_amount` |
- **الآثار:** رفع التجميد
- **العكس:** `لا يوجد إلا بتسوية يدوية معتمدة`

### `CHARGEBACK_LOST_OFFICE_LIABLE`

- **متى:** خسارة اعتراض والمسؤولية على المكتب
- **المصدر:** `chargeback_decision`
- **الشروط:** سبب المسؤولية موثق
- **حسم الحساب:** يخفض payable؛ وإن لم يكف ينشئ other receivable

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `2010_OFFICE_PAYABLE_OR_1030` | `loss_amount` |
| `C` | `1040_CHARGEBACK_RECEIVABLE` | `loss_amount` |
- **الآثار:** negative balance hierarchy
- **العكس:** `CHARGEBACK_DECISION_REVERSED`

### `CHARGEBACK_LOST_PLATFORM_LIABLE`

- **متى:** خسارة اعتراض بسبب فشل المنصة
- **المصدر:** `chargeback_decision`
- **الشروط:** قرار مسؤولية موثق

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `5020_FRAUD_LOSS` | `loss_amount` |
| `C` | `1040_CHARGEBACK_RECEIVABLE` | `loss_amount` |
- **الآثار:** تسجيل خسارة منصة
- **العكس:** `CHARGEBACK_DECISION_REVERSED`

### `CUSTOMER_COMPENSATION_APPROVED`

- **متى:** تعويض إضافي يتحمله طرف محدد
- **المصدر:** `dispute_decision`
- **الشروط:** ليس استرداد سعر التذكرة نفسه؛ اعتماد حسب الحد
- **حسم الحساب:** منصة=5010؛ مكتب=خفض 2010 أو زيادة 1030

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `5010_CUSTOMER_COMPENSATION_OR_OFFICE_PAYABLE` | `amount` |
| `C` | `2020_REFUND_PAYABLE` | `amount` |
- **الآثار:** إنشاء payout/refund task
- **العكس:** `COMPENSATION_CANCELLED`

### `SUBSCRIPTION_INVOICED`

- **متى:** استحقاق اشتراك مكتب
- **المصدر:** `subscription_invoice`
- **الشروط:** خطة/فترة snapshot

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1030_OTHER_RECEIVABLE` | `amount` |
| `C` | `4010_SUBSCRIPTION_REVENUE` | `amount` |
- **الآثار:** invoice open
- **العكس:** `SUBSCRIPTION_CREDIT_NOTE`

### `SUBSCRIPTION_PAID`

- **متى:** قبض اشتراك المكتب
- **المصدر:** `subscription_payment`
- **الشروط:** مرجع فريد

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `1000_BANK` | `amount` |
| `C` | `1030_OTHER_RECEIVABLE` | `amount` |
- **الآثار:** invoice paid
- **العكس:** `SUBSCRIPTION_PAYMENT_REVERSED`

### `BAD_DEBT_WRITE_OFF`

- **متى:** اعتماد شطب ذمة مكتب بعد إجراءات التحصيل
- **المصدر:** `writeoff`
- **الشروط:** اعتماد مزدوج؛ office terminated/collection exhausted

| الطرف | الحساب | المبلغ |
|---|---|---|
| `D` | `5030_BAD_DEBT` | `amount` |
| `C` | `1020_OR_1030_RECEIVABLE` | `amount` |
- **الآثار:** لا حذف للسجل
- **العكس:** `BAD_DEBT_RECOVERY`

## Invariants قابلة للاختبار

- لكل `ledger_entry`: مجموع D = مجموع C وبنفس العملة.
- لا posting بقيمة صفر أو سالبة.
- لا تعديل/حذف لقيد `posted`.
- `booking.paid_amount - refunded_amount` يطابق صافي الحركات الناجحة بعد المصالحة.
- `office payable + reserve held + office receivable netting` يطابق عناصر التسوية.
- مجموع `CUSTOMER_FUNDS` المفتوح يساوي أموال حجوزات لم تُنفذ ولم تُسترد.
- لا يصبح `commission=paid` دون Settlement item وقيد payout/netting.

## المصالحة اليومية

1. مطابقة provider events مع payment transactions.
2. مطابقة PSP receivable مع كشف المزود والبنك.
3. مطابقة إجمالي الحجوزات المدفوعة مع CUSTOMER_FUNDS.
4. مطابقة الحجوزات المكتملة مع commissions وOFFICE_PAYABLE/receivable.
5. قائمة فروقات لا تغلق تلقائيًا، مع مالك وسبب وموعد حسم.
