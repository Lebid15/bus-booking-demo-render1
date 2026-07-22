# التخزين والملفات

- Buckets منفصلة حسب البيئة والغرض.
- مفاتيح عشوائية ومسارات لا تكشف PII.
- Metadata في DB، والملف في Object Storage.
- حالات: initiated, uploaded, quarantined, clean, rejected, expired, deleted.
- Signed GET/PUT قصيرة العمر.
- Lifecycle rules للنسخ المؤقتة والمرفوضة.
- فحص Integrity checksum، وتدقيق الوصول للمستندات المقيدة.
