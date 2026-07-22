# G12 Traceability — Platform Administration and Reporting

| Capability | Implementation | Evidence |
|---|---|---|
| Office search and supervision | `organizations.views.PlatformOfficeListView`, `adminops.views.PlatformOfficeDetailView` | `tests/test_g12_admin_reporting.py` |
| Idempotent status control | `adminops.views.PlatformOfficeStatusView`, `OfficeStatusAction` | status replay and history test |
| Canonical office violations | `support.OfficeViolation` through `PlatformOfficeViolationListCreateView` | canonical-domain and close-command test |
| Central audit search | `adminops.views.PlatformAuditView` over append-only `AuditLog` | API route and OpenAPI contract |
| Platform summary | `PlatformReportsSummaryView` | functional `/platform/reports` surface |
| Tenant-scoped office summary | `OfficeReportsSummaryView` deriving office from authenticated context | foreign `office_id` isolation test |
| Web operations | `/platform/offices`, `/platform/audit`, `/platform/reports`, `/office/reports` | ESLint, TypeScript, Next.js build |
