import os
from pathlib import Path

import pytest

from daily_briefing import cli, mailer
from daily_briefing.vault import encrypt

KEY = "k" * 32


def make_workspace(root: Path) -> Path:
    (root / "sections").mkdir(parents=True)
    (root / "sections" / "10-research.md").write_text(
        "---\ntitle: Research\nicon: 🧠\n---\nMax 3.\n", encoding="utf-8"
    )
    (root / "state").mkdir()
    (root / "state" / "seen.md").write_text("# Seen\n", encoding="utf-8")
    (root / "interests.md").write_text("# Interests\n", encoding="utf-8")
    return root


@pytest.fixture
def ws(tmp_path):
    return make_workspace(tmp_path / "ws")


def test_guard_writes_skip_false_then_true(ws, tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ws))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("BRIEFING_TIMEZONE", "UTC")
    assert cli.main(["guard"]) == 0
    assert out.read_text().strip() == "skip=false"
    from datetime import UTC, datetime

    today = datetime.now(UTC).date().isoformat()
    (ws / "briefings").mkdir()
    (ws / "briefings" / f"{today}.md").write_text("# done")
    out.write_text("")
    assert cli.main(["guard"]) == 0
    assert out.read_text().strip() == "skip=true"
    monkeypatch.setenv("BRIEFING_FORCE", "true")
    out.write_text("")
    cli.main(["guard"])
    assert out.read_text().strip() == "skip=false"


def test_validate_ok_and_broken(ws, capsys):
    assert cli.main(["validate", "--dir", str(ws)]) == 0
    assert "1 section" in capsys.readouterr().out
    (ws / "sections" / "20-bad.md").write_text("no front matter", encoding="utf-8")
    assert cli.main(["validate", "--dir", str(ws)]) == 1
    assert "20-bad" in capsys.readouterr().out


def test_validate_requires_interests(ws, capsys):
    (ws / "interests.md").unlink()
    assert cli.main(["validate", "--dir", str(ws)]) == 1
    assert "interests.md" in capsys.readouterr().out


def test_preview_writes_html(ws, tmp_path):
    md = tmp_path / "b.md"
    md.write_text("# Daily briefing — Mon\n\n## Research\nHi\n", encoding="utf-8")
    out = tmp_path / "p.html"
    assert cli.main(["preview", str(md), "--sections", str(ws / "sections"), "-o", str(out)]) == 0
    html = out.read_text(encoding="utf-8")
    assert "🧠" not in html and "Mon" in html
    assert "<h2" in html and ">Research</h2>" in html


def test_run_end_to_end_with_fake_codex(ws, fake_codex, monkeypatch):
    (ws / ".briefing").mkdir()
    (ws / ".briefing" / "codex-auth.enc").write_bytes(encrypt(b'{"valid": true}', KEY))
    sent = []
    monkeypatch.setattr(mailer, "send", lambda message, settings: sent.append(message))
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_WORKSPACE": str(ws),
        "SMTP_USER": "me@example.com",
        "SMTP_PASSWORD": "pw",
        "BRIEFING_KEY": KEY,
        "BRIEFING_TIMEZONE": "UTC",
        "CODEX_BIN": str(fake_codex),
        "CODEX_HOME": str(ws.parent / "codex-home"),
        "GITHUB_EVENT_NAME": "schedule",
    }
    for key in list(os.environ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert cli.main(["run"]) == 0
    assert len(sent) == 1
    assert sent[0]["Subject"] == "Daily briefing — Test"
    html = sent[0].get_body(("html",)).get_content()
    assert "🧠" not in html and ">Research</h2>" in html
    assert any((ws / "briefings").glob("*.md"))


def test_guard_without_auth_key_skips_with_notice(ws, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ws))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("BRIEFING_TIMEZONE", "UTC")
    monkeypatch.setenv("HAS_AUTH_KEY", "false")
    assert cli.main(["guard"]) == 0
    assert out.read_text().strip() == "skip=true"
    printed = capsys.readouterr().out
    assert "::notice::Add the SMTP_USER, SMTP_PASSWORD and BRIEFING_KEY secrets" in printed


def _git(cwd, *args):
    import subprocess

    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def persist_env(ws, tmp_path, monkeypatch):
    import subprocess

    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True
    )
    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.name", "T")
    _git(ws, "config", "user.email", "t@x")
    _git(ws, "remote", "add", "origin", str(remote))
    _git(ws, "add", ".")
    _git(ws, "commit", "-m", "init")
    _git(ws, "push", "origin", "main")
    (ws / "state" / "seen.md").write_text("# Seen\nedited by codex\n", encoding="utf-8")
    (ws / ".briefing").mkdir()
    (ws / ".briefing" / "notified.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(ws))
    monkeypatch.setenv("BRIEFING_TIMEZONE", "UTC")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    for name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "BRIEFING_KEY"):
        monkeypatch.delenv(name, raising=False)
    return ws, remote


def _pushed_files(remote):
    return _git(remote, "ls-tree", "-r", "--name-only", "main").split()


def test_persist_without_todays_archive_leaves_state_out(persist_env):
    ws, remote = persist_env
    assert cli.main(["persist"]) == 0
    files = _pushed_files(remote)
    assert ".briefing/notified.json" in files
    remote_seen = _git(remote, "show", "main:state/seen.md")
    assert "edited by codex" not in remote_seen


def test_persist_with_todays_archive_pushes_state(persist_env):
    from datetime import UTC, datetime

    ws, remote = persist_env
    today = datetime.now(UTC).date().isoformat()
    (ws / "briefings").mkdir()
    (ws / "briefings" / f"{today}.md").write_text("# done", encoding="utf-8")
    assert cli.main(["persist"]) == 0
    assert "edited by codex" in _git(remote, "show", "main:state/seen.md")
    assert f"briefings/{today}.md" in _pushed_files(remote)
