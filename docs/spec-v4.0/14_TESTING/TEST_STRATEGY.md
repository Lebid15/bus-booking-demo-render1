# استراتيجية الاختبار

## الهرم

- Unit لقواعد السياسة والحساب والتحقق.
- Domain/Model tests للقيود والحالات.
- PostgreSQL integration للتزامن والمعاملات.
- Contract tests لـOpenAPI والمزودين.
- E2E للتدفقات الحرجة عبر واجهة حقيقية.
- Manual visual/accessibility/operational review.
- Recovery drills.

## بوابة Pull Request

Lint، types، unit، migrations check، integration subset، OpenAPI validation، security scan. لا يسمح بتخطي اختبارات P0 بسبب بطء دون خطة إصلاح.

## بيانات الاختبار

Factories قابلة للتكرار، تواريخ وتوقيتات صريحة، مكاتب متعددة لاختبار العزل، وعملات/سياسات مختلفة. لا تستخدم بيانات إنتاج حقيقية.

## التغطية ذات الأولوية

المقاعد، الدفع، Ledger، الصعود، العزل، Snapshot، الاسترداد، تغيير البولمان، Offline sync.
