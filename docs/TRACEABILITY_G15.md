# G15 / E16 Traceability — Platform Governance and Oversight

| Acceptance criterion | Implementation | Automated evidence | Result |
|---|---|---|---|
| `E16-AC01` Support role cannot view or modify settlements without finance permission | Explicit `PlatformRoleAssignment`, permission-aware `HasPlatformAccess`, separated `platform.support` and `platform.finance` roles | `test_e16_ac01_support_role_cannot_view_or_modify_settlements` | PASS |
| `E16-AC02` Critical office suspension stops new bookings without losing existing bookings | `PlatformActionApproval`, dual-control office status service, status-aware public sale guards, immutable existing bookings | `test_e16_ac02_critical_suspension_stops_new_sales_and_preserves_existing_booking` | PASS |
| `E16-AC03` Dispute decision contains reason, financial effect and appeal right | `FinancialDisputeDecision`, one-time `FinancialDisputeAppeal`, balanced ledger effect and independent appeal reviewer | `test_e16_ac03_dispute_decision_records_reason_financial_effect_and_one_appeal` | PASS |
| `E16-AC04` Sensitive platform mutation requires MFA and a second approver | Fresh-MFA check, requester/approver separation and executable `PlatformActionApproval` | `test_e16_ac04_critical_platform_change_requires_mfa_and_second_actor` | PASS |
| `E16-AC05` Financial reports reconcile to the ledger rather than UI aggregates | Platform and office reports aggregate `LedgerPosting` by currency and expose balance evidence | `test_e16_ac05_platform_financial_report_is_derived_from_ledger` | PASS |

## Additional closure evidence

| Control | Evidence | Result |
|---|---|---|
| Production cannot rely on legacy platform-admin fallback | `identity.checks.identity_deployment_checks`; production deploy check executed with fallback disabled | PASS |
| Pending approval operations are reviewable and executable | `GET /v1/platform/approvals`; `POST /v1/platform/approvals/{approval_id}/commands`; `/platform/approvals` | PASS |
| Office dispute response and one appeal are isolated to office context | office dispute services and `/office/disputes` console | PASS |
| Platform dispute financial effect requires an additional finance permission | `platform.dispute.manage` and `platform.dispute.finance` separation | PASS |
| API contract | Generated and validated `docs/evidence/G15-platform-governance/openapi-generated.yaml` | PASS |
| Clean migration | All migrations applied from an empty database, including identity/adminops/finance G15 migrations | PASS locally |
