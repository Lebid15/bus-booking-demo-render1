# النشر وCI/CD

## البيئات

Local، CI، Staging، Production. لا تستخدم بيانات إنتاج حقيقية في Staging دون إخفاء.

## Pipeline

Lint/type check → unit → PostgreSQL integration → migrations check → OpenAPI contract → security scans → build images → deploy staging → E2E → approval → production canary/rolling → smoke tests.

## قواعد Migration

Expand/Contract، تجنب أقفال طويلة، backfill مجزأ، قياس على نسخة مماثلة، وعدم حذف حقل قبل توقف كل قارئ له.

## الرجوع

Rollback للتطبيق، وRoll-forward للبيانات غالبًا. Feature Flag/Kill Switch للميزات عالية المخاطر.
