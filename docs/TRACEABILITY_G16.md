# G16 / E17 Traceability — Subscriptions and Plans

| Acceptance criterion | Implementation | Automated evidence | Result |
|---|---|---|---|
| `E17-AC01` An office subscription preserves the selected plan, price, features, limits and billing period as a snapshot | `SubscriptionPlan`, `OfficeSubscription`, `assign_subscription`, immutable period snapshots and invoice creation | `test_e17_ac01_assignment_saves_plan_price_features_limits_and_period_snapshot` | PASS |
| `E17-AC02` Expiry restricts new commercial actions without deleting existing bookings or customer rights | status progression `past_due -> grace -> expired`, centralized subscription sale guard, capacity guards and preserved booking rows | `test_e17_ac02_expiry_preserves_existing_booking_and_restricts_new_sales` | PASS |
| `E17-AC03` Collecting a subscription invoice posts balanced `SUBSCRIPTION_INVOICED` and `SUBSCRIPTION_PAID` ledger events | `create_invoice`, `mark_invoice_paid`, balanced posting specifications and payment-reference uniqueness | `test_e17_ac03_paid_invoice_posts_balanced_invoiced_and_paid_entries` | PASS |
| `E17-AC04` A later plan-price change does not rewrite a previously paid subscription period | plan version and price snapshots stored on `OfficeSubscription`; plan updates create forward-looking versions | `test_e17_ac04_plan_price_change_does_not_rewrite_paid_period_snapshot` | PASS |

## Additional closure evidence

| Control | Evidence | Result |
|---|---|---|
| Trial can be consumed only once per office | historical subscription lookup and `SUBSCRIPTION_TRIAL_ALREADY_USED` | PASS |
| Existing installations can migrate without an immediate outage | enforcement remains dormant until at least one active plan exists, then becomes mandatory | PASS |
| Plan usage limits are enforced server-side | branch, staff, vehicle and monthly-trip capacity guards | PASS |
| Renewal and expiry are background-safe | idempotent `subscriptions.process_due_subscriptions` Celery task every five minutes | PASS |
| Office plan changes remain reviewable | `SubscriptionChangeRequest` with immediate/next-period mode and platform review commands | PASS |
| Invoice correction preserves ledger history | void/uncollectible commands post a credit-note reversal instead of mutating posted entries | PASS |
| API contract | generated and validated `docs/evidence/G16-subscriptions/openapi-generated.yaml` | PASS |
| Clean migration | all migrations applied from an empty database, including `subscriptions.0001_initial` | PASS locally |
