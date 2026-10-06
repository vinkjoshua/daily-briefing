"""Encrypt the saved Codex login with a passphrase (scrypt + AES-GCM)."""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"DBV1"
_SALT, _NONCE, _TAG = 16, 12, 16


class VaultError(Exception):
    """Raised when a vault file cannot be decrypted."""


def _derive(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt(data: bytes, passphrase: str) -> bytes:
    """Encrypt bytes.

    Args:
        data: Plaintext, e.g. auth.json contents.
        passphrase: The BRIEFING_KEY secret.

    Returns:
        MAGIC + salt + nonce + ciphertext-with-tag.
    """
    salt, nonce = os.urandom(_SALT), os.urandom(_NONCE)
    return MAGIC + salt + nonce + AESGCM(_derive(passphrase, salt)).encrypt(nonce, data, MAGIC)


def decrypt(blob: bytes, passphrase: str) -> bytes:
    """Decrypt bytes produced by encrypt.

    Args:
        blob: Vault file contents.
        passphrase: The BRIEFING_KEY secret.

    Returns:
        The plaintext.

    Raises:
        VaultError: If the blob is not a vault file, the key is wrong or the data was altered.
    """
    header = len(MAGIC) + _SALT + _NONCE
    if not blob.startswith(MAGIC) or len(blob) < header + _TAG:
        raise VaultError("not a daily-briefing login file")
    salt = blob[len(MAGIC) : len(MAGIC) + _SALT]
    nonce = blob[len(MAGIC) + _SALT : header]
    try:
        return AESGCM(_derive(passphrase, salt)).decrypt(nonce, blob[header:], MAGIC)
    except InvalidTag as exc:
        raise VaultError("wrong BRIEFING_KEY or corrupted login file") from exc
