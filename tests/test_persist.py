import subprocess
from pathlib import Path

import pytest

from daily_briefing.persist import (
    PersistError,
    _redact,
    authenticated_url,
    commit_and_push,
)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repos(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True
    )
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    for repo in (work,):
        git(repo, "config", "user.name", "T")
        git(repo, "config", "user.email", "t@x")
    (work / "interests.md").write_text("v1\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "init")
    git(work, "push", "origin", "HEAD:main")
    return remote, work


def remote_files(remote: Path, tmp_path: Path) -> Path:
    check = tmp_path / "check"
    subprocess.run(["git", "clone", str(remote), str(check)], check=True, capture_output=True)
    return check


def test_only_allowlisted_paths_committed(repos, tmp_path):
    remote, work = repos
    (work / "state").mkdir()
    (work / "state" / "seen.md").write_text("item\n")
    (work / ".briefing").mkdir()
    (work / ".briefing" / "codex-auth.enc").write_bytes(b"DBV1x")
    (work / ".github" / "workflows").mkdir(parents=True)
    (work / ".github" / "workflows" / "evil.yml").write_text("on: push\n")
    (work / "interests.md").write_text("tampered\n")
    assert commit_and_push(work, "chore: briefing", branch="main") is True
    check = remote_files(remote, tmp_path)
    assert (check / "state" / "seen.md").read_text() == "item\n"
    assert (check / ".briefing" / "codex-auth.enc").is_file()
    assert not (check / ".github").exists()
    assert (check / "interests.md").read_text() == "v1\n"
    assert git(check, "log", "-1", "--format=%an") == "github-actions[bot]"


def test_nothing_to_commit(repos):
    _, work = repos
    assert commit_and_push(work, "chore: briefing", branch="main") is False


def test_push_rebases_over_remote_changes(repos, tmp_path):
    remote, work = repos
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    git(other, "config", "user.name", "U")
    git(other, "config", "user.email", "u@x")
    (other / "interests.md").write_text("edited on github\n")
    git(other, "commit", "-am", "edit interests")
    git(other, "push", "origin", "HEAD:main")
    (work / "briefings").mkdir()
    (work / "briefings" / "2026-10-07.md").write_text("# hi\n")
    assert commit_and_push(work, "chore: briefing", branch="main") is True
    check = remote_files(remote, tmp_path)
    assert (check / "interests.md").read_text() == "edited on github\n"
    assert (check / "briefings" / "2026-10-07.md").is_file()


def test_rebase_survives_dirty_tracked_file(repos, tmp_path):
    remote, work = repos
    (work / "notes.md").write_text("n1\n")
    git(work, "add", "notes.md")
    git(work, "commit", "-m", "notes")
    git(work, "push", "origin", "HEAD:main")
    other = tmp_path / "other2"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    git(other, "config", "user.name", "U")
    git(other, "config", "user.email", "u@x")
    (other / "interests.md").write_text("remote edit\n")
    git(other, "commit", "-am", "edit")
    git(other, "push", "origin", "HEAD:main")
    (work / "notes.md").write_text("local junk Codex left behind\n")
    (work / "state").mkdir()
    (work / "state" / "seen.md").write_text("x\n")
    assert commit_and_push(work, "chore: briefing", branch="main") is True
    check = remote_files(remote, tmp_path)
    assert (check / "state" / "seen.md").is_file()
    assert (check / "notes.md").read_text() == "n1\n"


def test_prestaged_files_outside_allowlist_not_committed(repos, tmp_path):
    remote, work = repos
    # Case 1: Pre-stage evil.yml, create state/seen.md, both should be handled correctly
    (work / ".github" / "workflows").mkdir(parents=True)
    (work / ".github" / "workflows" / "evil.yml").write_text("on: push\n")
    git(work, "add", ".github")
    (work / "state").mkdir()
    (work / "state" / "seen.md").write_text("item\n")
    assert commit_and_push(work, "chore: briefing", branch="main") is True
    check = remote_files(remote, tmp_path)
    assert (check / "state" / "seen.md").read_text() == "item\n"
    assert not (check / ".github").exists()

    # Case 2: Only non-allowlisted file pre-staged
    work2 = tmp_path / "work2"
    subprocess.run(["git", "clone", str(remote), str(work2)], check=True, capture_output=True)
    git(work2, "config", "user.name", "T")
    git(work2, "config", "user.email", "t@x")
    (work2 / ".github" / "workflows").mkdir(parents=True)
    (work2 / ".github" / "workflows" / "evil.yml").write_text("on: push\n")
    git(work2, "add", ".github")
    assert commit_and_push(work2, "chore: briefing", branch="main") is False


def test_push_failure_raises_with_token_and_includes_cause(repos):
    _, work = repos
    (work / "state").mkdir()
    (work / "state" / "x.md").write_text("x")
    remote_with_token = authenticated_url("https://example.invalid", "ann/r", "secret123")
    with pytest.raises(PersistError) as info:
        commit_and_push(
            work,
            "m",
            branch="main",
            remote=remote_with_token,
            token="secret123",
            retries=1,
        )
    error_msg = str(info.value)
    assert "secret123" not in error_msg
    assert "failed" in error_msg.lower()


def test_push_failure_with_retries_redacts_token(repos):
    _, work = repos
    (work / "state").mkdir()
    (work / "state" / "x.md").write_text("x")
    remote_with_token = authenticated_url("https://example.invalid", "ann/r", "secret123")
    with pytest.raises(PersistError) as info:
        commit_and_push(
            work,
            "m",
            branch="main",
            remote=remote_with_token,
            token="secret123",
            retries=2,
        )
    error_msg = str(info.value)
    assert "secret123" not in error_msg
    assert "failed" in error_msg.lower()


def test_redact_replaces_token():
    input_text = "error: https://x-access-token:secret123@github.com/r.git"
    expected = "error: https://x-access-token:***@github.com/r.git"
    assert _redact(input_text, "secret123") == expected
    assert _redact("secret123 in the middle secret123", "secret123") == "*** in the middle ***"
    assert _redact("no secret here", "") == "no secret here"
    assert _redact("secret123", "secret123") == "***"


def test_push_error_redacts_token_from_git_output(repos, monkeypatch):
    import daily_briefing.persist

    _, work = repos
    (work / "state").mkdir()
    (work / "state" / "x.md").write_text("x")

    original_run = subprocess.run
    call_count = {"push": 0, "pull": 0}

    def mock_run(args, **kwargs):
        if "push" in args:
            call_count["push"] += 1
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="fatal: could not read from https://x-access-token:secret123@github.com/ann/r.git",
            )
        elif "pull" in args:
            call_count["pull"] += 1
            return subprocess.CompletedProcess(
                args=args,
                returncode=1,
                stdout="",
                stderr="fatal: could not read from https://x-access-token:secret123@github.com/ann/r.git",
            )
        return original_run(args, **kwargs)

    monkeypatch.setattr(daily_briefing.persist.subprocess, "run", mock_run)

    remote_with_token = authenticated_url("https://github.com", "ann/r", "secret123")
    with pytest.raises(PersistError) as info:
        commit_and_push(
            work,
            "m",
            branch="main",
            remote=remote_with_token,
            token="secret123",
            retries=2,
        )
    error_msg = str(info.value)
    assert "secret123" not in error_msg
    assert "***" in error_msg
    assert call_count["push"] >= 1
    assert call_count["pull"] >= 1


def test_authenticated_url():
    assert (
        authenticated_url("https://github.com", "ann/b", "ghs_x")
        == "https://x-access-token:ghs_x@github.com/ann/b.git"
    )


def test_include_narrows_the_allowlist(repos, tmp_path):
    remote, work = repos
    (work / "state").mkdir()
    (work / "state" / "seen.md").write_text("x\n")
    (work / ".briefing").mkdir()
    (work / ".briefing" / "notified.json").write_text("{}")
    assert commit_and_push(work, "m", branch="main", include=("briefings", ".briefing")) is True
    check = remote_files(remote, tmp_path)
    assert not (check / "state").exists()
    assert (check / ".briefing" / "notified.json").is_file()


def test_include_rejects_paths_outside_allowlist(repos):
    _, work = repos
    with pytest.raises(ValueError):
        commit_and_push(work, "m", branch="main", include=("state", ".github"))


def test_failing_git_hooks_do_not_block_persist(repos):
    _, work = repos
    hook = work / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    (work / "state").mkdir()
    (work / "state" / "seen.md").write_text("x\n")
    assert commit_and_push(work, "m", branch="main") is True
