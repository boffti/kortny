"""Encrypted secret helpers for dashboard-managed credentials."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretEncryptionError(RuntimeError):
    """Raised when a configured secret key cannot encrypt or decrypt values."""


def encrypt_secret_value(value: str, *, encryption_key: str) -> bytes:
    """Encrypt a plaintext secret using the deployment encryption key."""

    if not value.strip():
        raise SecretEncryptionError("Secret value cannot be blank")
    encrypted: bytes = _fernet(encryption_key).encrypt(value.encode("utf-8"))
    return encrypted


def decrypt_secret_value(ciphertext: bytes, *, encryption_key: str) -> str:
    """Decrypt a stored secret value using the deployment encryption key."""

    try:
        plaintext = _fernet(encryption_key).decrypt(ciphertext)
    except InvalidToken as exc:
        raise SecretEncryptionError("Secret could not be decrypted") from exc
    decoded: str = plaintext.decode("utf-8")
    return decoded


def _fernet(encryption_key: str) -> Fernet:
    key = encryption_key.strip()
    if not key:
        raise SecretEncryptionError("ENCRYPTION_KEY is required")
    encoded = key.encode("utf-8")
    try:
        return Fernet(encoded)
    except Exception:
        # Accept high-entropy passphrases as a self-hosting convenience while
        # still using Fernet for authenticated encryption at rest.
        derived = base64.urlsafe_b64encode(hashlib.sha256(encoded).digest())
        return Fernet(derived)
