# عزل المكاتب والصلاحيات

## القاعدة

لا يرسل العميل `office_id` لتحديد نطاقه في عمليات المكتب. يستنتج الخادم المكتب والفرع من العضوية والجلسة، ويطبق Query Scopes مركزية.

## دفاع متعدد الطبقات

- Manager/Repository يفرض Tenant filters.
- Permission service يقرر الفعل والكيان والنطاق.
- قيود Foreign Keys تمنع ربط كيان بمكتب آخر.
- اختبارات سلبية لكل Endpoint.
- Audit لأي محاولة عبور نطاق.

## صلاحيات نموذجية

- `office.trip.manage`
- `office.booking.create`
- `office.payment.confirm_manual`
- `office.boarding.scan`
- `office.finance.view`
- `office.refund.request`
- `office.refund.approve`
- `platform.office.verify`
- `platform.settlement.approve`
- `platform.audit.view`

## فصل الواجبات

منشئ الاسترداد فوق العتبة لا يعتمد طلبه. تعديل حساب التسوية يحتاج مستخدمًا ثانيًا أو Cooling Period. لا يستطيع الدعم تعديل Ledger مباشرة.
