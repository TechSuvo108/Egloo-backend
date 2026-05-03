"""
Fernet symmetric encryption helpers for storing OAuth tokens securely in DB.
The ENCRYPTION_KEY in Settings must be a valid 32-byte URL-safe base64-encoded
key (generate with: Fernet.generate_key()).
"""

import base64
import os
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


def _get_fernet() -> Fernet:
    """Build a Fernet instance from the configured ENCRYPTION_KEY.

    If the key is a raw 32-byte hex string or any other non-base64 format,
    we derive a valid Fernet key by URL-safe base64-encoding the first 32 bytes
    of its SHA-256 digest so startup never crashes on a plaintext placeholder.
    """
    key: str = settings.ENCRYPTION_KEY
    try:
        # Try it as-is (already a proper Fernet key)
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        # Derive a stable key from whatever string is configured
        import hashlib

        raw = hashlib.sha256(key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(raw)
        return Fernet(fernet_key)


def encrypt_token(plain_text: str) -> str:
    """Encrypt *plain_text* and return a URL-safe base64 ciphertext string."""
    fernet = _get_fernet()
    return fernet.encrypt(plain_text.encode()).decode()


def decrypt_token(cipher_text: str) -> str:
    """Decrypt a previously encrypted ciphertext back to the original string.

    Raises:
        cryptography.fernet.InvalidToken – if decryption fails (wrong key /
        tampered data).
    """
    fernet = _get_fernet()
    return fernet.decrypt(cipher_text.encode()).decode()
