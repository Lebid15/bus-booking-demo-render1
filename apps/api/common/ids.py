from __future__ import annotations

import secrets
import time

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_public_id() -> str:
    """Generate a sortable 26-character ULID-compatible identifier."""
    timestamp_ms = int(time.time() * 1000)
    randomness = secrets.randbits(80)
    value = (timestamp_ms << 80) | randomness
    chars: list[str] = []
    for _ in range(26):
        chars.append(CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))
