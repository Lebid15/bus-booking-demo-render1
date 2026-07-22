from __future__ import annotations

import re

ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().casefold()


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    translated = value.translate(ARABIC_INDIC).strip()
    cleaned = re.sub(r"[^0-9+]", "", translated)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        cleaned = "+963" + cleaned[1:] if cleaned.startswith("0") and len(cleaned) >= 9 else "+" + cleaned
    if not re.fullmatch(r"\+[1-9]\d{7,14}", cleaned):
        raise ValueError("Invalid E.164 phone number")
    return cleaned


def normalize_identifier(value: str) -> tuple[str, str]:
    value = value.strip()
    if "@" in value:
        normalized = normalize_email(value)
        if normalized is None:
            raise ValueError("Identifier is required")
        return "email", normalized
    normalized_phone = normalize_phone(value)
    if normalized_phone is None:
        raise ValueError("Identifier is required")
    return "phone_e164", normalized_phone
