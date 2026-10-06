import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from daily_briefing import cli


def git(root, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=check
    ).stdout.strip()


@pytest.fixture
def instance(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    root = tmp_path / "instance"
    git(tmp_path, "init", "--bare", str(remote))
    shutil.copytree(Path(__file__).parents[1] / "template", root)
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Tester")
    git(root, "config", "user.email", "tester@example.com")
    git(root, "config", "gc.auto", "0")
    git(root, "config", "maintenance.auto", "false")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initial briefing")
    git(root, "remote", "add", "origin", "https://github.com/tester/briefing.git")
    # Git remains real: rewrite only the authenticated network URL to a local bare repo.
    git(root, "config", f"url.{remote}.insteadOf", "https://github.com/tester/briefing.git")
    git(root, "push", "origin", "main")
    account = tmp_path / "account.json"
    account.write_text(json.dumps({"login": "tester", "id": 42}))
    info = tmp_path / "repo.json"
    info.write_text(
        json.dumps(
            {
                "nameWithOwner": "tester/briefing",
                "isPrivate": True,
                "owner": {"login": "tester"},
                "defaultBranchRef": {"name": "main"},
            }
        )
    )
    calls = tmp_path / "calls.jsonl"
    fake = tmp_path / "gh"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "a = sys.argv[1:]\n"
        "with open(os.environ['PUBLISH_CALLS'], 'a') as f: f.write(json.dumps(a)+'\\n')\n"
        "if a == ['api', 'user']: print(pathlib.Path(os.environ['PUBLISH_ACCOUNT']).read_text())\n"
        "elif a[:2] == ['repo', 'view']:\n"
        " print(pathlib.Path(os.environ['PUBLISH_REPO']).read_text())\n"
        "elif a[:2] == ['workflow', 'run']: sys.exit(int(os.environ.get('DISPATCH_FAIL', '0')))\n"
        "else: sys.exit(97)\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PUBLISH_CALLS", str(calls))
    monkeypatch.setenv("PUBLISH_ACCOUNT", str(account))
    monkeypatch.setenv("PUBLISH_REPO", str(info))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    from daily_briefing import bootstrap

    monkeypatch.setattr(bootstrap, "ensure_tool", lambda tool: fake)
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")
    return root, remote, info, calls


def publish(root, **kwargs):
    return importlib.import_module("daily_briefing.publish").publish(root, **kwargs)


def edit(root, text="\nResearch quantum sensing.\n"):
    with (root / "interests.md").open("a") as f:
        f.write(text)


def bot(instance, tmp_path, path="state/watchlist.md", text="bot update\n"):
    _, remote, _, _ = instance
    clone = tmp_path / "bot"
    git(tmp_path, "clone", "--branch", "main", str(remote), str(clone))
    git(clone, "config", "user.name", "Bot")
    git(clone, "config", "user.email", "bot@example.com")
    with (clone / path).open("a") as f:
        f.write(text)
    git(clone, "add", path)
    git(clone, "commit", "-m", "Daily bot update")
    git(clone, "push", "origin", "main")
    return clone


def test_reviewed_commit_and_new_file_are_pushed(instance, capsys):
    root, remote, _, _ = instance
    edit(root)
    (root / "sections/99-new.md").write_text("---\ntitle: Extra\n---\nNew section.\n")
    assert publish(root) == 0
    assert "Research quantum sensing" in git(remote, "show", "main:interests.md")
    assert "New section" in git(remote, "show", "main:sections/99-new.md")
    assert "quantum sensing" in capsys.readouterr().out
    assert git(root, "status", "--porcelain") == ""
    assert (
        git(root, "config", "--get", "remote.origin.url")
        == "https://github.com/tester/briefing.git"
    )


def test_outgoing_commits_are_reviewed_without_new_commit(instance, capsys):
    root, remote, _, _ = instance
    edit(root)
    git(root, "add", "interests.md")
    git(root, "commit", "-m", "My accepted research")
    head = git(root, "rev-parse", "HEAD")
    assert publish(root) == 0
    assert git(remote, "rev-parse", "main") == head
    assert "My accepted research" in capsys.readouterr().out


@pytest.mark.parametrize(
    "path", ["auth.json", ".env", "preview.html", "briefings/leak.md", ".briefing/auth.enc"]
)
def test_forbidden_path_anywhere_in_history_stops_before_review(instance, path, monkeypatch):
    root, remote, _, _ = instance
    file = root / path
    file.parent.mkdir(exist_ok=True)
    file.write_text("secret")
    git(root, "add", "-f", path)
    git(root, "commit", "-m", "Add accidental file")
    file.unlink()
    git(root, "add", "-u")
    git(root, "commit", "-m", "Delete accidental file")
    before = git(remote, "rev-parse", "main")
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("must reject before review"))
    assert publish(root) == 1
    assert git(remote, "rev-parse", "main") == before


def test_partial_staging_is_preserved(instance, monkeypatch):
    root, remote, _, _ = instance
    edit(root, "\nstaged\n")
    git(root, "add", "interests.md")
    edit(root, "\nunstaged\n")
    index = (root / ".git/index").read_bytes()
    before = git(remote, "rev-parse", "main")
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("must reject staged work"))
    assert publish(root) == 1
    assert (root / ".git/index").read_bytes() == index
    assert git(remote, "rev-parse", "main") == before
    assert "unstaged" in (root / "interests.md").read_text()


def test_unrelated_dirty_file_is_preserved(instance):
    root, _, _, _ = instance
    (root / "notes.txt").write_text("my unrelated work")
    head = git(root, "rev-parse", "HEAD")
    assert publish(root) == 1
    assert git(root, "rev-parse", "HEAD") == head
    assert (root / "notes.txt").read_text() == "my unrelated work"


def test_cancellation_preserves_files_and_head(instance, monkeypatch):
    root, remote, _, _ = instance
    edit(root)
    before = git(root, "rev-parse", "HEAD")
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert publish(root) == 130
    assert git(root, "rev-parse", "HEAD") == before
    assert git(remote, "rev-parse", "main") == before
    assert "quantum sensing" in (root / "interests.md").read_text()
    assert git(root, "diff", "--cached") == ""


@pytest.mark.parametrize(
    "field,value",
    [
        ("isPrivate", False),
        ("nameWithOwner", "other/briefing"),
        ("owner", {"login": "other"}),
        ("defaultBranchRef", None),
    ],
)
def test_remote_identity_failure_prevents_local_mutations(instance, field, value):
    root, _, info, _ = instance
    metadata = json.loads(info.read_text())
    metadata[field] = value
    info.write_text(json.dumps(metadata))
    edit(root)
    before = git(root, "rev-parse", "HEAD")
    assert publish(root) == 1
    assert git(root, "rev-parse", "HEAD") == before
    assert not (root / ".git/FETCH_HEAD").exists()


@pytest.mark.parametrize("mode", ["detached", "branch", "orphan", "merge"])
def test_unsupported_history_stops_without_local_commit(instance, mode):
    root, _, _, _ = instance
    if mode == "detached":
        git(root, "checkout", "--detach")
    elif mode == "branch":
        git(root, "checkout", "-b", "custom")
    elif mode == "orphan":
        git(root, "checkout", "--orphan", "other")
        git(root, "commit", "-m", "Unrelated root")
        git(root, "branch", "-M", "main")
    else:
        git(root, "checkout", "-b", "feature")
        edit(root)
        git(root, "add", "interests.md")
        git(root, "commit", "-m", "Feature")
        git(root, "checkout", "main")
        git(root, "merge", "--no-ff", "feature", "-m", "Custom merge")
    before = git(root, "rev-parse", "HEAD")
    edit(root)
    assert publish(root) == 1
    assert git(root, "rev-parse", "HEAD") == before


def test_bot_fast_forward_and_noop_dispatch(instance, tmp_path):
    root, remote, _, calls = instance
    bot(instance, tmp_path)
    assert publish(root, run=True) == 0
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")
    dispatch = [
        a for a in map(json.loads, calls.read_text().splitlines()) if a[:2] == ["workflow", "run"]
    ]
    assert dispatch == [
        ["workflow", "run", "briefing.yml", "--repo", "tester/briefing", "--ref", "main"]
    ]


def test_nonconflicting_bot_rebase_is_reviewed_again(instance, tmp_path, monkeypatch):
    root, remote, _, _ = instance
    bot(instance, tmp_path)
    edit(root)
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "yes")
    assert publish(root) == 0
    assert "bot update" in git(remote, "show", "main:state/watchlist.md")
    assert "quantum sensing" in git(remote, "show", "main:interests.md")
    assert len(prompts) == 2


def test_conflict_aborts_rebase_and_preserves_reviewed_local_commit(instance, tmp_path, capsys):
    root, remote, _, _ = instance
    bot(instance, tmp_path, "interests.md", "\nRemote research.\n")
    edit(root)
    assert publish(root) == 1
    assert "quantum sensing" in git(root, "show", "HEAD:interests.md")
    assert "Remote research" in git(remote, "show", "main:interests.md")
    assert not (root / ".git/rebase-merge").exists()
    assert git(root, "status", "--porcelain") == ""
    output = capsys.readouterr().out
    assert "rebase" in output and "conflict" in output.lower()


def test_push_rejection_preserves_commit_and_safe_retry(instance, capsys):
    root, remote, _, _ = instance
    hook = remote / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    edit(root)
    assert publish(root, run=True) == 1
    local = git(root, "rev-parse", "HEAD")
    assert local != git(remote, "rev-parse", "main")
    assert "inspect" in capsys.readouterr().out.lower()
    hook.unlink()
    assert publish(root) == 0
    assert git(remote, "rev-parse", "main") == local


def test_symlink_in_worktree_and_history_is_rejected(instance):
    root, _, _, _ = instance
    file = root / "sections/99-link.md"
    file.symlink_to(root / "interests.md")
    assert publish(root) == 1
    git(root, "add", str(file))
    git(root, "commit", "-m", "Add link")
    file.unlink()
    git(root, "add", "-u")
    git(root, "commit", "-m", "Delete link")
    assert publish(root) == 1


def test_ssh_origin_uses_scoped_https_without_global_helper(instance):
    root, remote, _, _ = instance
    git(root, "remote", "set-url", "origin", "git@github.com:tester/briefing.git")
    edit(root)
    assert publish(root) == 0
    assert git(remote, "rev-parse", "main") == git(root, "rev-parse", "HEAD")
    assert git(root, "remote", "get-url", "origin") == "git@github.com:tester/briefing.git"
    assert git(root, "config", "--get", "credential.helper", check=False) == ""


def test_dispatch_failure_is_reported_once_without_retry(instance, monkeypatch, capsys):
    root, _, _, calls = instance
    monkeypatch.setenv("DISPATCH_FAIL", "1")
    assert publish(root, run=True) == 1
    assert "uncertain" in capsys.readouterr().out.lower()
    assert (
        sum(a[:2] == ["workflow", "run"] for a in map(json.loads, calls.read_text().splitlines()))
        == 1
    )


def test_publish_cli_uses_current_instance(instance, monkeypatch):
    root, remote, _, _ = instance
    monkeypatch.chdir(root)
    edit(root)
    assert cli.main(["publish"]) == 0
    assert git(root, "rev-parse", "HEAD") == git(remote, "rev-parse", "main")


def test_second_review_cannot_publish_a_new_unreviewed_commit(instance, tmp_path, monkeypatch):
    root, remote, _, _ = instance
    bot(instance, tmp_path)
    edit(root)
    count = 0

    def answer(prompt):
        nonlocal count
        count += 1
        if count == 2:
            edit(root, "\nUnreviewed later change.\n")
            git(root, "add", "interests.md")
            git(root, "commit", "-m", "Not reviewed")
        return "yes"

    monkeypatch.setattr("builtins.input", answer)
    assert publish(root) == 1
    assert "Unreviewed later change" not in git(remote, "show", "main:interests.md")
    assert "Unreviewed later change" in git(root, "show", "HEAD:interests.md")


def test_identity_fallback_supports_rebase_without_global_changes(instance, tmp_path, monkeypatch):
    root, remote, _, _ = instance
    bot(instance, tmp_path)
    git(root, "config", "--unset", "user.name")
    git(root, "config", "--unset", "user.email")
    git(root, "config", "user.useConfigOnly", "true")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    edit(root)
    assert publish(root) == 0
    assert (
        git(remote, "log", "-1", "--format=%an <%ae>", "main")
        == "tester <42+tester@users.noreply.github.com>"
    )


def test_remote_advances_during_review_and_retry_rebases(instance, tmp_path, monkeypatch):
    root, remote, _, _ = instance
    edit(root)
    monkeypatch.setattr("builtins.input", lambda _: bot(instance, tmp_path) and "yes")
    assert publish(root) == 1
    assert "quantum sensing" not in git(remote, "show", "main:interests.md")
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    assert publish(root) == 0
    assert "bot update" in git(remote, "show", "main:state/watchlist.md")
    assert "quantum sensing" in git(remote, "show", "main:interests.md")


def test_replacement_refs_cannot_hide_forbidden_outgoing_commit(instance):
    root, remote, _, _ = instance
    initial = git(root, "rev-parse", "HEAD")
    (root / "auth.json").write_text("secret")
    git(root, "add", "auth.json")
    git(root, "commit", "-m", "Forbidden")
    forbidden = git(root, "rev-parse", "HEAD")
    (root / "auth.json").unlink()
    git(root, "add", "-u")
    git(root, "commit", "-m", "Remove")
    git(root, "replace", forbidden, initial)
    assert publish(root) == 1
    assert git(remote, "rev-parse", "main") == initial


def test_scoped_gh_helper_is_used_for_real_git_transport(instance, monkeypatch, tmp_path):
    root, _, _, _ = instance
    trace = tmp_path / "trace"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))
    edit(root)
    assert publish(root) == 0
    recorded = trace.read_text()
    assert "credential.helper=" in recorded
    assert "credential.https://github.com.helper=" in recorded
    assert "auth git-credential" in recorded
    assert '"push","https://github.com/tester/briefing.git","HEAD:refs/heads/main"' in recorded


@pytest.mark.parametrize("invalid", ["section", "workflow", "ancestor", "origin", "state_link"])
def test_invalid_instance_is_not_committed(instance, tmp_path, invalid):
    root, _, _, _ = instance
    before = git(root, "rev-parse", "HEAD")
    edit(root)
    if invalid == "section":
        (root / "sections/10-research.md").write_text("invalid section")
    elif invalid == "workflow":
        path = root / ".github/workflows/briefing.yml"
        path.write_text(path.read_text().replace('timezone: "UTC"', 'timezone: "${{ env.TZ }}"'))
    elif invalid == "ancestor":
        nested = root / "nested"
        shutil.copytree(root, nested, ignore=shutil.ignore_patterns(".git", "nested"))
        root = nested
    elif invalid == "origin":
        git(root, "remote", "set-url", "origin", "https://token@github.com/tester/briefing.git")
    else:
        shutil.rmtree(root / "state")
        (root / "state").symlink_to(tmp_path, target_is_directory=True)
    assert publish(root) == 1
    assert git(root, "rev-parse", "HEAD") == before


def test_bot_update_cannot_overwrite_ignored_local_work(instance, tmp_path):
    root, remote, _, _ = instance
    clone = bot(instance, tmp_path)
    (clone / ".briefing").mkdir(exist_ok=True)
    (clone / ".briefing/local.enc").write_text("remote encrypted login")
    git(clone, "add", "-f", ".briefing/local.enc")
    git(clone, "commit", "-m", "Bot encrypted login")
    git(clone, "push", "origin", "main")
    (root / ".briefing").mkdir(exist_ok=True)
    (root / ".briefing/local.enc").write_text("my local ignored work")
    with (root / ".git/info/exclude").open("a") as f:
        f.write("\n.briefing/local.enc\n")
    before = git(root, "rev-parse", "HEAD")
    assert publish(root) == 1
    assert (root / ".briefing/local.enc").read_text() == "my local ignored work"
    assert git(root, "rev-parse", "HEAD") == before
    assert git(remote, "rev-parse", "main") != before


def test_intent_to_add_index_is_preserved(instance):
    root, _, _, _ = instance
    (root / "sections/99-new.md").write_text("---\ntitle: New\n---\nNew topic.\n")
    git(root, "add", "--intent-to-add", "sections/99-new.md")
    index = (root / ".git/index").read_bytes()
    assert publish(root) == 1
    assert (root / ".git/index").read_bytes() == index


def test_cancel_after_rebase_keeps_local_commits_without_pushing(instance, tmp_path, monkeypatch):
    root, remote, _, calls = instance
    bot(instance, tmp_path)
    remote_head = git(remote, "rev-parse", "main")
    edit(root)
    answers = iter(["yes", "no"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert publish(root, run=True) == 130
    assert "quantum sensing" in git(root, "show", "HEAD:interests.md")
    assert git(remote, "rev-parse", "main") == remote_head
    assert not any(
        a[:2] == ["workflow", "run"] for a in map(json.loads, calls.read_text().splitlines())
    )
