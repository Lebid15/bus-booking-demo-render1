# G17 / E18 Traceability — Continuity, Monitoring and Release

| Acceptance criterion | Implementation | Automated / practical evidence | Result |
|---|---|---|---|
| `E18-AC01` PostgreSQL failure stops bookings and changes; Redis is never accepted as source of truth | `ContinuityWriteGuardMiddleware`, database-aware health handling, platform modes `maintenance/recovery/reconciliation`, PostgreSQL remains the authoritative seat/payment/ledger store | `test_e18_ac01_recovery_mode_blocks_writes_but_not_reads`; `continuity-practical.log` shows writes returning `503 PLATFORM_MAINTENANCE` while reads remain available | PASS locally |
| `E18-AC02` Recovery exercise proves `RPO <= 15m` and `RTO <= 4h`, otherwise records a failed release gate | `BackupRun`, `RecoveryExercise`, calculated RPO/RTO, backup/restore scripts | `test_e18_ac02_recovery_exercise_enforces_rpo_and_rto`; `migrate-fresh.log` | PASS locally; real PITR drill remains a staging gate |
| `E18-AC03` Seats, payments and ledger reconcile before reopening sales | `ReconciliationRun`, explicit seat/payment/ledger conflict counters, reopen guard | `test_e18_ac03_reopen_requires_successful_reconciliation`; practical recovery cycle recorded 0/0/0 conflicts before reopening | PASS |
| `E18-AC04` Failed Health/Smoke requires rollback | `ReleaseRun`, health/smoke result, mandatory rollback reference, smoke and rollback scripts | `test_e18_ac04_failed_smoke_requires_and_records_rollback`; failed runs cannot leave an orphan release row | PASS |
| `E18-AC05` SEV-1 has commander, timeline, communication channel and postmortem | `Incident`, `IncidentTimelineEntry`, commander/channel guards and close guard | `test_e18_ac05_sev1_requires_commander_timeline_communications_and_postmortem` | PASS |
| `E18-AC06` Launch load gate respects SLOs with zero duplicate seats or financial entries | `LoadTestRun`, p95/error-rate SLOs and duplicate counters | `test_e18_ac06_load_gate_rejects_duplicate_seats_or_financial_entries` | PASS contractually; representative production-like load remains a staging gate |

## Additional closure evidence

| Control | Evidence | Result |
|---|---|---|
| Ready health includes database, cache and continuity state | `/health/ready`, `test_ready_health_includes_continuity_state` | PASS |
| Fresh database bootstrap | all migrations, permissions and 120 notification templates seeded from an empty SQLite database | PASS locally |
| Release API and operations console | `/v1/platform/continuity*`, `/v1/platform/releases`, `/v1/platform/incidents`, `/v1/platform/load-tests`, `/platform/continuity` | PASS |
| Operational scripts | `backup_postgres.sh`, `restore_postgres.sh`, `smoke_release.sh`, `rollback_release.sh` | PRESENT and executable |
| CI coverage | PostgreSQL 18, Redis, migrations, checks, tests, deploy check, OpenAPI and dependency audit | CONFIGURED |
