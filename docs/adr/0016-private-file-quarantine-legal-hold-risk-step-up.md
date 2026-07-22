# ADR 0016 — Private file quarantine, Legal Hold and risk Step-up

## Status

Accepted for G14 Release Candidate.

## Context

The platform handles office documents, identity evidence, transfer proofs and support attachments. It must also support data-subject deletion requests without destroying legally mandatory booking/finance history, and it must respond proportionally to fraud signals rather than silently blocking every uncertain booking.

## Decision

### Private files

1. The authenticated session and office membership determine ownership; callers never choose an `office_id` for file scope.
2. Purpose-specific allowlists validate filename extension, MIME and size before an upload URL is issued.
3. New objects are addressed only under a random quarantine key.
4. Completion locks the metadata row, invokes a pluggable scanner and validates detected MIME, size and SHA-256.
5. Only a clean result promotes the object key to private final storage. Rejected files remain quarantined for controlled evidence retention.
6. Cross-tenant lookups return the same generic not-found envelope used for nonexistent files.

### Privacy and retention

1. Account deletion is a data-subject workflow, not destructive cascading deletion.
2. The account is disabled, credentials and active sessions/devices are revoked, and unnecessary identity/contact fields are anonymised.
3. Booking, commission, ledger and settlement records remain intact where legally/financially mandatory.
4. An active Legal Hold supersedes retention deletion for the specific subject. Every skip and release is audited.

### Fraud controls

1. Risk assessment is persisted before the booking decision.
2. Low risk proceeds; medium risk receives Step-up; higher risk enters manual review or block according to configured thresholds.
3. Step-up challenges are attempt-limited and expiry-bound. Successful verification yields a hashed, one-time token tied to the booking subject.
4. The verified retry consumes the token and records a new allow assessment; it does not rewrite the original risk decision.

### Audit hygiene

Audit values are recursively redacted by sensitive key fragments and free-text patterns. Safe hashes and last-four values remain visible for investigation, while bearer/JWT tokens, PAN/CVV, passwords, OTPs, cookies, sessions and private/API keys are removed.

## Consequences

- Object storage and malware scanning remain replaceable infrastructure contracts.
- Production deployment is rejected when storage/scanner/Step-up configuration is still on development defaults.
- Legal Hold can delay deletion and therefore requires operational ownership and legal review.
- Risk Step-up introduces a second request round trip but avoids unjustified automatic denial.
