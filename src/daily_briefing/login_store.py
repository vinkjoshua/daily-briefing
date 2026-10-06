"""Move the Codex login between the encrypted repo file and CODEX_HOME."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from daily_briefing.vault import VaultError, decrypt, encrypt

AUTH_FILE = "auth.json"
_MARKER = ".restored-sha256"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def restore_login(blob_path: Path, codex_home: Path, key: str) -> bool:
    """Decrypt the saved login into CODEX_HOME.

    Args:
        blob_path: Encrypted login file in the repo.
        codex_home: Codex home directory; created if missing.
        key: BRIEFING_KEY.

    Returns:
        True if a login was restored; False if there is none or it cannot be decrypted.
    """
    codex_home.mkdir(parents=True, exist_ok=True)
    if not blob_path.is_file():
        return False
    try:
        data = decrypt(blob_path.read_bytes(), key)
    except VaultError:
        return False
    target = codex_home / AUTH_FILE
    fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    target.chmod(0o600)
    (codex_home / _MARKER).write_text(_digest(data), encoding="utf-8")
    return True


def save_login_if_changed(blob_path: Path, codex_home: Path, key: str) -> bool:
    """Re-encrypt the login into the repo if Codex refreshed or created it.

    Args:
        blob_path: Encrypted login file in the repo.
        codex_home: Codex home directory.
        key: BRIEFING_KEY.

    Returns:
        True if the encrypted file was (re)written.
    """
    source = codex_home / AUTH_FILE
    if not source.is_file():
        return False
    data = source.read_bytes()
    marker = codex_home / _MARKER
    digest = _digest(data)
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == digest:
        return False
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(encrypt(data, key))
    marker.write_text(digest, encoding="utf-8")
    return True
