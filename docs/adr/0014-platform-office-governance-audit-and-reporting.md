# ADR 0014 — Platform office governance, audit, and reporting

Platform office status changes are explicit append-only actions with a mandatory reason and audit before/after state. Violations are separate records rather than flags on the office, preserving history and evidence. Reports query operational source tables and never accept an office identifier for office-user scope; tenant scope is derived from membership. Platform audit output exposes redacted metadata only.
