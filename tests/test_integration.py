"""Exercise the onboarding-to-publication flow without external services."""

import importlib
import json

from daily_briefing import cli, local
from daily_briefing.codex import Codex
from daily_briefing.github import git as real_git
from test_local import snapshot
from test_publish import bot, git
from test_setup import answers, initial
from test_setup import setup_env as setup_env


def test_setup_resume_preview_and_publish_after_bot_update(
    setup_env, tmp_path, monkeypatch, fake_codex, capsys
):
    setup, github, root, smtp = setup_env
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "--bare", str(remote))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def transport(directory, *args, gh_bin=None, check=True):
        if args[0] == "push":
            assert set(github.secrets) == {"SMTP_USER", "SMTP_PASSWORD", "BRIEFING_KEY"}
            git(root, "config", f"url.{remote}.insteadOf", "https://github.com/alice/daily.git")
            github.events.append(("push",))
        result = real_git(directory, *args, gh_bin=gh_bin, check=check)
        if args[0] == "push":
            github.repo.update(isEmpty=False, defaultBranchRef={"name": "main"})
        return result

    monkeypatch.setattr(setup, "git", transport)
    answers(monkeypatch, initial(root, launch="y"))
    assert cli.main(["init", str(root)]) == 0
    assert "Cloud run queued:" in capsys.readouterr().out
    assert smtp.instances[0].calls[0] == ("login", "a@example.com", "abcdefgh")
    assert git(remote, "rev-parse", "main") == git(root, "rev-parse", "HEAD")
    assert git(root, "ls-files", "--stage", "briefing").startswith("100755 ")
    assert git(remote, "show", "main:.github/workflows/briefing.yml")
    assert github.events.index(("push",)) > max(
        index for index, event in enumerate(github.events) if event[:2] == ("secret", "set")
    )

    before = snapshot(root)
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert cli.main(["init", str(root)]) == 0
    assert snapshot(root) == before
    assert sum(event[:2] == ("workflow", "run") for event in github.events) == 1

    home = tmp_path / "auth"
    home.mkdir()
    (home / "auth.json").write_text('{"valid": true}')
    log = tmp_path / "codex-calls.jsonl"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(local, "ensure_tool", lambda _: fake_codex)
    monkeypatch.setattr(
        local,
        "Codex",
        lambda binary, auth, workdir: Codex(
            binary, auth, workdir, extra_env={"FAKE_CODEX_LOG": str(log)}
        ),
    )
    monkeypatch.chdir(root)
    assert cli.main(["validate", "--dir", "."]) == 0
    assert cli.main(["try", "--section", "10-research"]) == 0
    after = snapshot(root)
    assert b"Hello" in after.pop("preview.html")
    assert after == before
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert "interests.md" in calls[-1]["prompt"] and "## This week" not in calls[-1]["prompt"]

    bot((root, remote, None, None), tmp_path)
    with (root / "interests.md").open("a") as file:
        file.write("\nResearch quantum sensing.\n")
    publication = importlib.import_module("daily_briefing.publish")
    monkeypatch.setattr(publication.bootstrap, "ensure_tool", lambda _: "/fake/gh")
    monkeypatch.setattr(publication, "run_gh", github.run)
    assert cli.main(["publish", "--run"]) == 0
    assert "quantum sensing" in git(remote, "show", "main:interests.md")
    assert "bot update" in git(remote, "show", "main:state/watchlist.md")
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")
    assert "preview.html" not in git(remote, "ls-tree", "-r", "--name-only", "main")
    assert git(root, "config", "--get", "remote.origin.url") == "https://github.com/alice/daily.git"
