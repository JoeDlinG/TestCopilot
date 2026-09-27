"""Lightweight symmetric encryption for at-rest secrets (e.g. AI API keys).

Uses Fernet (AES-128-CBC + HMAC) with a key derived from ``settings.ENCRYPTION_KEY``.
Tokens are stored as ``<b64 ciphertext>``. Plaintext that cannot be decrypted
(e.g. legacy unencrypted values already in the DB) is returned as-is so the
system keeps working during the migration.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    raw = settings.ENCRYPTION_KEY.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_value(plaintext: str | None) -> str | None:
    """Encrypt a plaintext secret. Returns ``None`` for empty input."""
    if not plaintext:
        return plaintext
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(token: str | None) -> str | None:
    """Decrypt a stored token. Falls back to returning the input unchanged
    when decryption fails, so pre-existing plaintext values still work."""
    if not token:
        return token
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token
