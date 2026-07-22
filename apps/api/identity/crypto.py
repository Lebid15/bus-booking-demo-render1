from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _key() -> bytes:
    configured = settings.MFA_ENCRYPTION_KEY.strip()
    if configured:
        return configured.encode()
    if settings.DEBUG or settings.APP_ENV in {"local", "test", "ci"}:
        return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    raise RuntimeError("MFA_ENCRYPTION_KEY is required outside debug mode")


def encrypt_secret(secret: str) -> bytes:
    return Fernet(_key()).encrypt(secret.encode())


def decrypt_secret(ciphertext: bytes) -> str:
    return Fernet(_key()).decrypt(ciphertext).decode()
