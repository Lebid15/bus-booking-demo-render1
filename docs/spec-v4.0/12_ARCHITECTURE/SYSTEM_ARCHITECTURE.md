# معمارية النظام

## النمط

Modular Monolith بحدود مجال واضحة، لأنه يقلل تعقيد التشغيل والمعاملات الموزعة في المرحلة الأولى، مع Outbox للأحداث الخارجية وإمكان فصل وحدات لاحقًا.

## التقنيات الأساسية

- Python 3.13.
- Django 5.2 LTS + Django REST Framework.
- Next.js 16 App Router + React 19 + TypeScript.
- PostgreSQL 18.
- Redis للحجز المؤقت والـCache والـrate limits، لا كمصدر مقاعد نهائي.
- Celery 5.6 للمهام الخلفية.
- S3-compatible private storage.
- ASGI/WebSocket/SSE للتحديثات الانتقائية.

Django 5.2 موثق كإصدار LTS، وNext.js وثائقه الحالية تعرض خط 16، وPostgreSQL 18 له وثائق إصدار رسمية، وCelery stable الحالي 5.6. تُثبت الإصدارات الدقيقة في lockfiles وتحدث عبر ADR واختبارات، لا في المواصفة التجارية.

## التطبيقات/الوحدات

identity، organizations، geography، fleet، scheduling، inventory، bookings، passengers، payments، tickets، boarding، finance، support، policies، notifications، risk، audit، reporting.

## التدفق

Browser → CDN/WAF → Next.js → Django API → PostgreSQL. Redis/Celery وخدمة الملفات والمزودون خلف API. Outbox ينقل الآثار الجانبية بعد Commit.
