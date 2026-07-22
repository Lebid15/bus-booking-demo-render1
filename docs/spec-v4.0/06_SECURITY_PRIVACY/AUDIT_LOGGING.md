# سجل التدقيق والتسجيل

## Audit Event

- event_id، occurred_at، actor_user_id، actor_type، office/branch scope.
- action، entity_type، entity_id.
- before/after diff مع حجب الأسرار.
- reason_code وrequest_id وIP/device metadata منخفضة الدقة.
- approval chain عند العمليات المزدوجة.

## أحداث إلزامية

تسجيل الدخول الحساس، تغيير دور، تعديل حساب تسوية، تأكيد دفع يدوي، استرداد، إلغاء رحلة، تغيير بولمان، تجاوز مقعد، نشر سياسة، تعليق مكتب، تصدير بيانات، واستخدام وصول طوارئ.

## Logs التشغيلية

Structured JSON، Correlation ID، مستويات واضحة، وعدم تسجيل كلمات مرور أو tokens أو بيانات بطاقة أو ملفات هوية. تحتفظ Logs التشغيلية مدة أقصر من Audit.
