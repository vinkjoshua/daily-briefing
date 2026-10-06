"""Recognise Codex login errors and parse the device-code login prompt."""

from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_AUTH = re.compile(
    r"401 Unauthorized|not logged in|refresh[_ ]token|invalid_grant|token[_ ]expired"
    r"|(?:log|sign) ?in again|please (?:log|sign) ?in",
    re.IGNORECASE,
)
_DEVICE_URL = re.compile(r"https://\S+/device\b\S*")
_DEVICE_CODE = re.compile(r"\b[A-Z0-9]{4}-[A-Z0-9]{4,6}\b")


def strip_ansi(text: str) -> str:
    """Remove terminal colour codes.

    Args:
        text: Text that may contain ANSI escape sequences.

    Returns:
        The text without escape sequences.
    """
    return _ANSI.sub("", text)


def is_auth_error(output: str) -> bool:
    """Tell whether Codex output indicates a missing or rejected login.

    Args:
        output: Combined stdout and stderr from a Codex run.

    Returns:
        True for login problems, False for anything else (rate limits, outages, bugs).
    """
    return bool(_AUTH.search(strip_ansi(output)))


def parse_device_prompt(output: str) -> tuple[str, str] | None:
    """Extract the login URL and one-time code from `codex login --device-auth` output.

    Args:
        output: Output printed so far.

    Returns:
        (url, code) once both are present, otherwise None.
    """
    text = strip_ansi(output)
    url = _DEVICE_URL.search(text)
    code = _DEVICE_CODE.search(text)
    return (url.group(0), code.group(0)) if url and code else None
