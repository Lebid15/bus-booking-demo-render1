# نموذج التهديدات

| التهديد | السيناريو | الضوابط |
|---|---|---|
| بيع مزدوج | طلبان على المقعد نفسه | Transaction + row/advisory lock + unique constraint |
| حجز وهمي | احتلال مقاعد متكرر | Hold قصير، limits، تحقق قناة، risk review |
| دفع مكرر | Webhook أو طلب مكرر | provider_event unique + idempotency key |
| تزوير تحويل | صورة قديمة أو معدلة | مرجع/وقت/مبلغ، مراجعة، سجل، حدود صلاحية |
| QR مسروق | مشاركة صورة التذكرة | token عشوائي، إصدار، إبطال، single-use، تحقق هوية عند الحاجة |
| عبور Tenant | تغيير ID في URL | scope خادمي، authorization، اختبارات IDOR |
| موظف داخلي | استرداد أو تغيير حساب | MFA، فصل واجبات، تنبيه، Audit |
| رفع ملف خبيث | مستند تحقق/تحويل | MIME sniffing، size limit، AV sandbox، private storage |
| تسريب Logs | PII في stack trace | structured logging، redaction، access control |
| Cache poisoning | الاعتماد على Redis كمصدر | PostgreSQL source of truth |
| Credential stuffing | محاولات دخول | rate limit، breached password checks، MFA |
| Chargeback مزدوج | Refund ثم اعتراض | cross-reference وfreeze ومنع double compensation |
