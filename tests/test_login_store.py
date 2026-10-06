import stat
from pathlib import Path
from unittest.mock import patch

from daily_briefing.login_store import AUTH_FILE, restore_login, save_login_if_changed
from daily_briefing.vault import decrypt, encrypt

KEY = "k" * 32


def test_restore_without_blob_returns_false(tmp_path):
    assert restore_login(tmp_path / "missing.enc", tmp_path / "home", KEY) is False
    assert (tmp_path / "home").is_dir()


def test_restore_writes_private_auth_file(tmp_path):
    blob = tmp_path / "auth.enc"
    blob.write_bytes(encrypt(b'{"a": 1}', KEY))
    home = tmp_path / "home"
    assert restore_login(blob, home, KEY) is True
    auth = home / AUTH_FILE
    assert auth.read_bytes() == b'{"a": 1}'
    assert stat.S_IMODE(auth.stat().st_mode) == 0o600


def test_restore_creates_auth_file_private_from_the_start(tmp_path):
    blob = tmp_path / "auth.enc"
    blob.write_bytes(encrypt(b'{"a": 1}', KEY))
    home = tmp_path / "home"
    with patch.object(Path, "chmod"):
        assert restore_login(blob, home, KEY) is True
        auth = home / AUTH_FILE
        assert stat.S_IMODE(auth.stat().st_mode) == 0o600


def test_restore_with_wrong_key_returns_false(tmp_path):
    blob = tmp_path / "auth.enc"
    blob.write_bytes(encrypt(b'{"a": 1}', KEY))
    home = tmp_path / "home"
    assert restore_login(blob, home, "x" * 32) is False
    assert not (home / AUTH_FILE).exists()


def test_save_skips_unchanged(tmp_path):
    blob = tmp_path / ".briefing" / "auth.enc"
    blob.parent.mkdir()
    blob.write_bytes(encrypt(b'{"a": 1}', KEY))
    home = tmp_path / "home"
    restore_login(blob, home, KEY)
    before = blob.read_bytes()
    assert save_login_if_changed(blob, home, KEY) is False
    assert blob.read_bytes() == before


def test_save_writes_refreshed_login(tmp_path):
    blob = tmp_path / ".briefing" / "auth.enc"
    blob.parent.mkdir()
    blob.write_bytes(encrypt(b'{"a": 1}', KEY))
    home = tmp_path / "home"
    restore_login(blob, home, KEY)
    (home / AUTH_FILE).write_bytes(b'{"a": 2}')
    assert save_login_if_changed(blob, home, KEY) is True
    assert decrypt(blob.read_bytes(), KEY) == b'{"a": 2}'


def test_save_first_login_creates_blob(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / AUTH_FILE).write_bytes(b'{"new": true}')
    blob = tmp_path / ".briefing" / "auth.enc"
    assert save_login_if_changed(blob, home, KEY) is True
    assert decrypt(blob.read_bytes(), KEY) == b'{"new": true}'


def test_save_without_login_does_nothing(tmp_path):
    assert save_login_if_changed(tmp_path / "auth.enc", tmp_path, KEY) is False
    assert not (tmp_path / "auth.enc").exists()
