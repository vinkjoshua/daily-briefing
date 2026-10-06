import json
import subprocess
import sys

import pytest

from daily_briefing import github


def fake_tool(tmp_path, body):
    binary = tmp_path / "tool with spaces"
    binary.write_text(f"#!{sys.executable}\n" + body)
    binary.chmod(0o755)
    return binary


def test_gh_preserves_arguments_and_sends_secret_on_stdin(tmp_path):
    binary = fake_tool(
        tmp_path, "import json, sys\nprint(json.dumps([sys.argv[1:], sys.stdin.read()]))\n"
    )
    result = github.run_gh(binary, ["secret", "set", "NAME"], input_text="private value")
    assert json.loads(result.stdout) == [["secret", "set", "NAME"], "private value"]
    assert result.returncode == 0


def test_gh_error_never_echoes_stdin_or_arguments(tmp_path):
    binary = fake_tool(
        tmp_path, "import sys\nprint(sys.stdin.read(), file=sys.stderr)\nsys.exit(7)\n"
    )
    with pytest.raises(github.CommandError) as error:
        github.run_gh(binary, ["unsafe argument"], input_text="super-secret")
    assert "7" in str(error.value)
    assert "super-secret" not in str(error.value)
    assert "unsafe argument" not in str(error.value)


def test_gh_unchecked_failure_returns_completed_process(tmp_path):
    binary = fake_tool(tmp_path, "import sys\nprint('failed', file=sys.stderr)\nsys.exit(9)\n")
    result = github.run_gh(binary, ["auth", "status"], check=False)
    assert result.returncode == 9 and result.stderr == "failed\n"


def test_gh_capture_false_inherits_output(tmp_path, capfd):
    binary = fake_tool(tmp_path, "print('visible')\n")
    result = github.run_gh(binary, [], capture=False)
    assert result.stdout is None and capfd.readouterr().out == "visible\n"


def test_missing_gh_is_actionable(tmp_path):
    with pytest.raises(github.CommandError, match="gh"):
        github.run_gh(tmp_path / "missing", [])


def test_git_disables_hooks_for_this_command(tmp_path):
    assert github.git(tmp_path, "config", "--get", "core.hooksPath").stdout.strip() == "/dev/null"
    result = subprocess.run(
        ["git", "-C", str(tmp_path), "config", "--local", "--get", "core.hooksPath"],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0


def test_git_scopes_credential_helper_and_handles_binary_path_spaces(tmp_path):
    binary = tmp_path / "gh with spaces"
    result = github.git(
        tmp_path,
        "config",
        "--get-urlmatch",
        "credential.helper",
        "https://github.com/owner/repo",
        gh_bin=binary,
    )
    helper = result.stdout.strip()
    assert "gh with spaces" in helper and "auth git-credential" in helper
    # Execute Git's shell command the way the credential subsystem does.
    binary.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\"\n")
    binary.chmod(0o755)
    completed = subprocess.run(
        ["/bin/sh", "-c", helper[1:] + " get"], text=True, capture_output=True
    )
    assert completed.stdout == "auth git-credential get\n"
    result = github.git(
        tmp_path,
        "config",
        "--get-urlmatch",
        "credential.helper",
        "https://elsewhere.example/owner/repo",
        gh_bin=binary,
        check=False,
    )
    assert "git-credential" not in result.stdout


def test_git_noninteractive_environment(tmp_path, monkeypatch):
    binary = fake_tool(
        tmp_path,
        "import os, json\nprint(json.dumps({k: os.getenv(k) for k in "
        "['GIT_TERMINAL_PROMPT', 'GCM_INTERACTIVE']}))\n",
    )
    directory = tmp_path / "bin"
    directory.mkdir()
    binary.rename(directory / "git")
    monkeypatch.setenv("PATH", str(directory))
    env = json.loads(github.git(tmp_path, "fetch").stdout)
    assert env == {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


def test_git_error_is_safe_and_check_false_returns_status(tmp_path):
    with pytest.raises(github.CommandError, match="git") as error:
        github.git(tmp_path, "bad-command", "private-argument")
    assert "private-argument" not in str(error.value)
    assert github.git(tmp_path, "bad-command", check=False).returncode != 0
