from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time


def generate_totp(secret: str, *, at_time: int | None = None, digits: int = 6, period: int = 30) -> str:
    timestamp = int(time.time() if at_time is None else at_time)
    counter = timestamp // period
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp(secret: str, code: str, *, at_time: int | None = None, window: int = 1) -> bool:
    now = int(time.time() if at_time is None else at_time)
    for delta in range(-window, window + 1):
        candidate = generate_totp(secret, at_time=now + delta * 30)
        if hmac.compare_digest(candidate, code.strip()):
            return True
    return False
