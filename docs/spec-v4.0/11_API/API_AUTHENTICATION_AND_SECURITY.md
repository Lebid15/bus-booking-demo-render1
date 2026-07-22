# المصادقة وأمن API

## أنماط الوصول

- Public read endpoints مع rate limits.
- Guest booking management عبر PNR + management token/verified contact، وليس PNR وحده للعمليات الحساسة.
- Customer session للحساب الاختياري.
- Office session/role مع Tenant scope.
- Platform session/role مع MFA وصلاحيات دقيقة.
- Provider webhooks بتوقيع ومفتاح دوران.

## الرؤوس

- `Authorization` أو Cookie جلسة حسب السطح.
- `Idempotency-Key` للعمليات الحساسة.
- `If-Match`/version للتعديلات المتزامنة.
- `X-Request-ID` في الطلب/الاستجابة.

## أخطاء الأمن

لا يميز الرد بين وجود حساب أو عدمه في الاستعادة. أخطاء عبور Tenant تعيد 404/403 وفق سياسة منع التسريب وتسجل داخليًا. لا تعيد الاستجابة Stack Trace أو معرفات مزود حساسة.
