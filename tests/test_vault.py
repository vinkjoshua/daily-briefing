import pytest

from daily_briefing.vault import VaultError, decrypt, encrypt

KEY = "correct horse battery staple 1234"


def test_round_trip():
    assert decrypt(encrypt(b'{"tokens": 1}', KEY), KEY) == b'{"tokens": 1}'


def test_ciphertext_is_random_and_opaque():
    first, second = encrypt(b"secret-token", KEY), encrypt(b"secret-token", KEY)
    assert first != second
    assert b"secret-token" not in first


def test_wrong_key():
    with pytest.raises(VaultError, match="BRIEFING_KEY"):
        decrypt(encrypt(b"x", KEY), KEY + "!")


def test_tampered():
    blob = bytearray(encrypt(b"x", KEY))
    blob[-1] ^= 1
    with pytest.raises(VaultError):
        decrypt(bytes(blob), KEY)


def test_garbage():
    with pytest.raises(VaultError, match="not a daily-briefing"):
        decrypt(b"hello", KEY)
