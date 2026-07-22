# معمارية الأمن

## المبادئ

- Zero Trust بين الأسطح والخدمات والمكاتب.
- أقل صلاحية وفصل واجبات للعمليات المالية والحساسة.
- PostgreSQL مصدر الحقيقة، وتُفرض القيود داخل قاعدة البيانات حيث أمكن.
- أسرار المزودين لا تصل إلى الواجهة ولا تحفظ كنص في Git.
- البيانات الحساسة لا تدخل Logs أو Analytics أو Error Messages.

## طبقات الحماية

1. WAF/Rate Limiting على الحواف.
2. TLS وإعدادات أمنية للرؤوس وCSP.
3. مصادقة وجلسات آمنة وMFA.
4. Authorization خادمي على كل عملية وTenant scope.
5. تحقق Schema وBusiness Guards.
6. معاملات وقيود فريدة ومفاتيح Idempotency.
7. تشفير التخزين الخاص والنسخ الاحتياطية.
8. Audit append-only ومراقبة وتنبيه.

## تصنيف البيانات

- Public: المدن والخطوط العامة.
- Internal: إعدادات تشغيل غير حساسة.
- Confidential: حجوزات واتصال وتقارير مكتب.
- Restricted: هوية، مستندات، حسابات تسوية، رموز إدارة، أسرار مزود.

## متطلبات النشر

- منع DEBUG في الإنتاج.
- قواعد CORS محددة، لا wildcard مع credentials.
- Cookies: Secure, HttpOnly, SameSite مناسب.
- CSP مع Nonces عند الحاجة.
- فحص Dependencies وImages وSecrets في CI.
- SAST/DAST واختبارات صلاحيات وعزل قبل الإصدار.
