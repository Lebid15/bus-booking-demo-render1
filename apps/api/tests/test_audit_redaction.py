from auditlog.services import _redact_string


def test_audit_redaction_preserves_uuid_identifiers() -> None:
    value = "5b2c4298-0127-4812-8652-708ada92410d"
    assert _redact_string(value) == value


def test_audit_redaction_masks_standalone_card_number() -> None:
    assert _redact_string("card 4111 1111 1111 1111") == "card [REDACTED_CARD]"
