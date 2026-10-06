"""Thin, private subprocess boundaries for GitHub CLI and Git commands."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


class CommandError(RuntimeError):
    """A command failed, with diagnostics that omit arguments, input and output."""


def _run(
    command: list[str],
    *,
    name: str,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command without allowing error diagnostics to echo secrets."""
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=capture,
            check=False,
            env=env,
            **({"stdin": subprocess.DEVNULL} if input_text is None else {}),
        )
    except OSError:
        raise CommandError(
            f"Could not run {name}; check the executable and its permissions."
        ) from None
    if check and result.returncode:
        raise CommandError(
            f"{name} failed (exit {result.returncode}); check authentication, permissions "
            "and the requested operation."
        )
    return result


def run_gh(
    binary: Path,
    args: list[str],
    *,
    input_text: str | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run GitHub CLI, passing any secret input solely through stdin.

    Args:
        binary: GitHub CLI executable.
        args: Command arguments, excluding secrets.
        input_text: Optional stdin text; never included in error diagnostics.
        capture: Capture stdout and stderr when true.
        check: Raise CommandError for a nonzero exit when true.

    Returns:
        Completed process with text output if captured.
    """
    return _run(
        [str(binary), *args], name="gh", input_text=input_text, capture=capture, check=check
    )


def git(
    root: Path,
    *args: str,
    gh_bin: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git without hooks or terminal credential prompts.

    Args:
        root: Git working directory.
        args: Git arguments, excluding secrets.
        gh_bin: Optional command-scoped credential helper for HTTPS github.com.
        check: Raise CommandError for a nonzero exit when true.

    Returns:
        Completed process with captured text output.
    """
    command = ["git", "-C", str(root), "-c", "core.hooksPath=/dev/null"]
    if gh_bin is not None:
        command += [
            "-c",
            "credential.helper=",
            "-c",
            f"credential.https://github.com.helper=!{shlex.quote(str(gh_bin))} auth git-credential",
        ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    return _run([*command, *args], name="git", check=check, env=env)
