# نتائج بوابة G1

التاريخ: 2026-07-21

## نتائج محلية منفذة

- تثبيت Python dependencies: PASS
- `python manage.py check`: PASS
- تطبيق المهاجرات على قاعدة SQLite نظيفة: PASS
- `makemigrations --check --dry-run`: PASS
- `ruff check apps/api`: PASS
- `mypy common identity organizations geography fleet auditlog config`: PASS
- `pytest`: **24 passed**
- OpenAPI generation/validation: PASS دون أخطاء، مع تحذيرات تسمية Enums غير كاسرة
- Bandit: PASS، لا ملاحظات متوسطة أو عالية
- `npm ci`: PASS، لا ثغرات npm معلنة
- `npm audit --audit-level=moderate`: PASS، 0 vulnerabilities
- `npm run lint`: PASS
- `npm run typecheck`: PASS
- `npm run build`: PASS، 9 صفحات

## حدود الدليل المحلي

Docker وPostgreSQL binaries غير متاحين داخل بيئة التنفيذ الحالية، لذلك لم يُنفذ اختبار PostgreSQL 18 محليًا. كما تعذر `pip-audit` محليًا بسبب فشل DNS نحو PyPI بعد اكتمال تثبيت الحزم؛ يبقى مفعلًا في CI. Workflow الـCI مهيأ لتشغيل المهاجرات والاختبارات نفسها على PostgreSQL 18 وRedis قبل الدمج. لا تعتبر بوابة PostgreSQL مغلقة حتى تنجح تلك الدورة.

## القرارات المؤجلة المقصودة

- الإخفاء العام لمكاتب `suspended` يُختبر End-to-End عند ظهور `trips/search` في E04/E05.
- Snapshot مخطط المقعد على الرحلة يُغلق عند بناء الرحلات في E04؛ الإصدار غير القابل للتعديل الرجعي جاهز الآن.
- صلاحيات موظفي المنصة الدقيقة ما زالت خلف `is_platform_staff` إلى أن تبنى إدارة موظفي المنصة؛ الأكواد معلنة على Endpoints للتتبع.
