"""Commit allowlisted state back to the instance repository."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ALLOWLIST = ("state", "briefings", ".briefing")
_BOT_NAME = "github-actions[bot]"
_BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class PersistError(Exception):
    """Raised when state cannot be pushed."""


def _redact(text: str, token: str) -> str:
    """Redact sensitive token from text.

    Args:
        text: Text that may contain the token.
        token: Secret token to redact.

    Returns:
        Text with token replaced by "***" if token is non-empty.
    """
    if token:
        return text.replace(token, "***")
    return text


def authenticated_url(server_url: str, repository: str, token: str) -> str:
    """Build an HTTPS push URL carrying the job token.

    Args:
        server_url: For example https://github.com.
        repository: owner/name.
        token: GITHUB_TOKEN.

    Returns:
        https://x-access-token:<token>@host/owner/name.git
    """
    host = urlsplit(server_url).netloc
    return f"https://x-access-token:{token}@{host}/{repository}.git"


def commit_and_push(
    root: Path,
    message: str,
    *,
    branch: str,
    remote: str = "origin",
    token: str = "",
    retries: int = 3,
    include: tuple[str, ...] = ALLOWLIST,
) -> bool:
    """Commit only ALLOWLIST paths and push, rebasing over concurrent edits.

    Args:
        root: Repository root.
        message: Commit message.
        branch: Branch to push to.
        remote: Remote name or URL.
        token: Secret to redact from error messages.
        retries: Push attempts.
        include: Subset of ALLOWLIST to commit; it can only narrow the set.

    Returns:
        True if a commit was pushed, False if there was nothing to commit.

    Raises:
        PersistError: If pushing fails after all retries.
        ValueError: If include has an entry outside ALLOWLIST.
    """
    extra = [p for p in include if p not in ALLOWLIST]
    if extra:
        raise ValueError(f"not in the persist allowlist: {extra}")

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if check and proc.returncode != 0:
            detail = _redact(proc.stderr or proc.stdout, token)
            raise PersistError(f"git {args[0]} failed: {detail.strip()}")
        return proc

    present = [p for p in include if (root / p).exists()]
    if not present:
        return False
    git("reset", "--quiet")
    git("add", "--", *present)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return False
    git("-c", f"user.name={_BOT_NAME}", "-c", f"user.email={_BOT_EMAIL}", "commit", "-m", message)
    last_push_error = ""
    for attempt in range(retries):
        push_proc = git("push", remote, f"HEAD:refs/heads/{branch}", check=False)
        if push_proc.returncode == 0:
            return True
        last_push_error = push_proc.stderr or push_proc.stdout
        if attempt < retries - 1:
            git(
                "-c",
                f"user.name={_BOT_NAME}",
                "-c",
                f"user.email={_BOT_EMAIL}",
                "pull",
                "--rebase",
                "--autostash",
                remote,
                branch,
            )
    error_detail = _redact(last_push_error, token).strip()
    if error_detail:
        raise PersistError(f"git push to {branch} failed: {error_detail}")
    raise PersistError(f"git push to {branch} failed after {retries} attempts")
