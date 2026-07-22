# OpenAPI Delta — G0

المواصفة الأصلية محفوظة دون تعديل في `docs/spec-v4.0/11_API/openapi.yaml`.

## إضافات الهوية

| Method | Path | السبب | المرجع |
|---|---|---|---|
| POST | `/v1/auth/register` | إنشاء حساب موحد بعد التطبيع ومنع التكرار | E01-AC01 |
| POST | `/v1/auth/register/verify` | تفعيل الحساب بعد التحقق من رمز القناة مع حد للمحاولات | E01-AC01 |
| DELETE | `/v1/me/sessions/{session_id}` | إنهاء جلسة محددة وتسجيل Audit | E01-AC05 |
| GET | `/health/live` | Liveness probe | G0 / Observability |
| GET | `/health/ready` | DB + Cache readiness | G0 / Observability |

هذه إضافات additive. لا يوجد تغيير كاسر في المسارات المعيارية القائمة.
