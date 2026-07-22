# G13 Traceability — E15 Notifications

| Acceptance criterion | Implementation | Automated evidence |
|---|---|---|
| E15-AC01 booking survives email failure and retries | Outbox consumer, independent `NotificationDelivery`, exponential backoff | `test_e15_ac01_booking_remains_successful_when_email_fails_and_retry_is_scheduled` |
| E15-AC02 republished event is deduplicated | semantic SHA-256 key includes aggregate, recipient, channel, template version | `test_e15_ac02_republished_event_does_not_duplicate_channel_and_template_version` |
| E15-AC03 material change requires explicit response | action-required notification and unchanged pending `TripChangeResponse` | `test_e15_ac03_material_change_notification_requires_explicit_response_and_silence_does_not_accept` |
| E15-AC04 exhausted channel escalates | SMS fallback plus P1 support case and escalation record | `test_e15_ac04_exhausted_critical_channel_creates_sms_fallback_and_human_escalation` |
| E15-AC05 language and version selection | latest published language-specific template with Arabic fallback | `test_e15_ac05_user_language_and_latest_published_template_version_are_used` |
| Template operations | `seed_notification_templates`, 120 default templates | clean database seed evidence |
| User inbox/preferences/Push | `/v1/me/notifications*`, `/v1/me/push-subscriptions` | serializers, API contract, `/notifications` UI |
| Office inbox | `/v1/office/notifications` | permission seed and `/office/notifications` UI |
| Delivery operations | list/filter/retry endpoints with stored Idempotency | `/platform/notifications` UI and OpenAPI |
| Scheduled execution | Celery Beat dispatch and delivery jobs every 5 seconds | settings and task registration |
