# خطة اختبارات الأمن والخصوصية

- IDOR عبر كل معرف مكتب/فرع/حجز/ملف.
- تجاوز الدور والصلاحية وفصل الواجبات.
- CSRF/XSS/CSP وحقن SQL/Template.
- brute force وcredential stuffing وrate limits.
- رفع ملفات مزدوجة الامتداد وMIME مزور وZip bomb.
- signed URL expiry وتسريب Referer.
- Logs خالية من PII/Secrets.
- حذف/تصدير حساب مع بيانات مالية.
- Tenant data export لا يتضمن مكتبًا آخر.
- Webhook signature/replay.
- إدارة جلسات وMFA وحساب تسوية.
