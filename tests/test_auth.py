import pytest

from daily_briefing.auth import is_auth_error, parse_device_prompt, strip_ansi

UNAUTHORIZED = (
    "ERROR: Reconnecting... 5/5\n"
    "ERROR: unexpected status 401 Unauthorized: Missing bearer or basic authentication in header,"
    " url: https://api.openai.com/v1/responses, cf-ray: a463bf5e48c84e47-AMS\n"
)
DEVICE_PROMPT = (
    "Welcome to Codex [v\x1b[90m0.160.0\x1b[0m]\n\n"
    "Follow these steps to sign in with ChatGPT using device code authorization:\n\n"
    "1. Open this link in your browser and sign in to your account\n"
    "   \x1b[94mhttps://auth.openai.com/codex/device\x1b[0m\n\n"
    "2. Enter this one-time code \x1b[90m(expires in 15 minutes)\x1b[0m\n"
    "   \x1b[94mABCD-12345\x1b[0m\n"
)


@pytest.mark.parametrize(
    "output",
    [UNAUTHORIZED, "Not logged in", "Your refresh token was revoked", "error: invalid_grant"],
)
def test_auth_errors_detected(output):
    assert is_auth_error(output)


@pytest.mark.parametrize(
    "output",
    ["", "ERROR: unexpected status 429 Too Many Requests", "stream disconnected before completion"],
)
def test_other_errors_not_auth(output):
    assert not is_auth_error(output)


def test_strip_ansi():
    assert strip_ansi("\x1b[94mhello\x1b[0m") == "hello"


def test_parse_device_prompt():
    assert parse_device_prompt(DEVICE_PROMPT) == (
        "https://auth.openai.com/codex/device",
        "ABCD-12345",
    )


def test_parse_device_prompt_incomplete():
    assert parse_device_prompt(DEVICE_PROMPT.split("2. Enter")[0]) is None
