# G14 / E14 Traceability — Security, Privacy and Fraud

| Acceptance criterion | Implementation | Automated evidence | Result |
|---|---|---|---|
| `E14-AC01` Office A cannot access Office B or receive sensitive metadata | `securityops.services._owner_for_user`, `_owned_file`, `UploadCompleteView` | `test_e14_ac01_cross_office_file_access_returns_generic_not_found_without_metadata` | PASS |
| `E14-AC02` Disallowed or infected file never enters final storage | Upload allowlist, `StoredFile` quarantine lifecycle, pluggable scanner, `complete_upload` | `test_e14_ac02_malware_file_remains_quarantined_and_never_enters_final_storage` | PASS |
| `E14-AC03` Account deletion anonymises nonessential data and preserves mandatory financial records | `request_account_deletion`, `_anonymize_user`, session/device revocation | `test_e14_ac03_account_deletion_anonymizes_identity_and_preserves_booking_and_finance` | PASS |
| `E14-AC04` Legal Hold makes retention deletion skip and audit the reason | `LegalHold`, `process_retention_requests`, Celery Beat task | `test_e14_ac04_retention_job_skips_legal_hold_and_audits_reason` | PASS |
| `E14-AC05` Medium risk requests step-up instead of final automatic block | `enforce_public_booking_risk`, `RiskChallenge`, verify endpoint and one-time token consumption | `test_e14_ac05_medium_risk_requests_step_up_then_allows_verified_booking` | PASS |
| `E14-AC06` Sensitive success/failure Audit is redacted | recursive key/pattern redaction in `auditlog.services` | `test_e14_ac06_sensitive_audit_redacts_nested_secrets_tokens_cvv_and_card_numbers` | PASS |

## Additional closure evidence

| Control | Evidence | Result |
|---|---|---|
| Production cannot start with fake private storage, no scanner or default Step-up code | `securityops.checks`; two deployment-check tests; `manage.py check --deploy --fail-level WARNING` | PASS |
| API contracts | Generated and validated `docs/evidence/G14-security-privacy/openapi-generated.yaml` | PASS |
| Clean migration | All migrations applied to a new SQLite database; PostgreSQL remains CI source-of-truth gate | PASS locally |
| UI surfaces | `/privacy` and `/platform/security` compile in the 34-route Next.js production build | PASS |
| Source quality | Ruff, strict Mypy, Bandit, secret/source cleanup | PASS |
