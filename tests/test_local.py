from datetime import date
from pathlib import Path

import pytest

from daily_briefing import cli, local
from daily_briefing.codex import CodexResult


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "interests.md").write_text("# Interests\nPhysics\n")
    (root / "sections").mkdir()
    for slug, title in [("10-research", "Research"), ("20-news", "News")]:
        (root / "sections" / f"{slug}.md").write_text(
            f"---\ntitle: {title}\nicon: 🧠\n---\nFind {title}.\n"
        )
    (root / "state").mkdir()
    (root / "state" / "seen.md").write_text("# Seen\n")
    (root / "state" / "watchlist.md").write_text("# Watchlist\n")
    workflow(root)
    return root


def workflow(
    root,
    inputs=(
        "timezone: Pacific/Auckland\n          model: gpt-test\n          reasoning-effort: medium"
    ),
    extra="",
):
    path = root / ".github" / "workflows" / "briefing.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "jobs:\n  briefing:\n    steps:\n"
        "      - uses: vinkjoshua/daily-briefing@v1\n        with:\n          "
        + inputs
        + "\n"
        + extra
    )


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("stage", ["probe", "generation"])
def test_try_interrupt_stops_processes_and_preserves_source(workspace, codex_tree, stage):
    (workspace / "preview.html").write_text("accepted preview")
    before = snapshot(workspace)
    result = codex_tree(
        "import os\nfrom daily_briefing import cli, local\n"
        f"os.chdir({str(workspace)!r})\n"
        "os.environ['CODEX_HOME'] = str(home)\n"
        "local.ensure_tool = lambda tool: Path(binary)\n"
        "def make_codex(binary, auth, workdir):\n"
        "    global preview_workdir\n    preview_workdir = workdir\n"
        "    return Codex(binary, auth, workdir, extra_env=extra)\n"
        "local.Codex = make_codex\n"
        "status = cli.main(['try'])\n"
        "assert not preview_workdir.exists(), 'preview workspace survived cancellation'\n"
        "sys.exit(status)\n",
        interrupt=True,
        exec_mode="hang-generation" if stage == "generation" else "hang-child",
    )
    assert result.returncode == 130
    assert "cancelled" in result.stdout.lower()
    assert "Traceback" not in result.stderr
    assert snapshot(workspace) == before


@pytest.mark.parametrize("section", [None, "10-research"])
def test_preview_uses_isolated_inputs_and_keeps_repo_unchanged(
    workspace, monkeypatch, tmp_path, section
):
    for name in [".git/config", ".briefing/codex-auth.enc", "briefings/old.md", "AGENTS.md"]:
        p = workspace / name
        p.parent.mkdir(exist_ok=True)
        p.write_text("must never copy")
    before = snapshot(workspace)
    home = tmp_path / "local-auth"
    home.mkdir()
    (home / "config.toml").write_text('cli_auth_credentials_store = "keyring"\n')
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-secret")
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))
    monkeypatch.setattr(
        local, "today_in", lambda tz: date(2026, 10, 8) if tz == "Pacific/Auckland" else None
    )
    observed = []

    class Fake:
        def __init__(self, binary, codex_home, workdir):
            assert codex_home == home
            self.root = workdir

        def probe(self):
            assert self.root != workspace
            assert snapshot(self.root) == {
                k: v
                for k, v in before.items()
                if k == "interests.md"
                or k.startswith("state/")
                or (
                    k.startswith("sections/") and (section is None or k == f"sections/{section}.md")
                )
            }
            return CodexResult(0, "OK")

        def exec(self, prompt, *, out_path, **kwargs):
            observed.append((prompt, kwargs))
            (self.root / "state" / "seen.md").write_text("changed in temp")
            out_path.write_text("# Daily briefing — Preview\n\n## Research\nPreview result\n")
            return CodexResult(0, "done")

    monkeypatch.setattr(local, "Codex", Fake)
    assert local.try_briefing(workspace, section=section) == 0
    after = snapshot(workspace)
    assert after.pop("preview.html") and after == before
    assert "Preview result" in (workspace / "preview.html").read_text()
    assert "Today is 2026-10-08." in observed[0][0]
    assert observed[0][1] == {"effort": "medium", "model": "gpt-test"}
    assert ("Find News." in observed[0][0]) == (section is None)


def test_workflow_literals_and_defaults(workspace):
    assert local.workflow_settings(workspace) == {
        "timezone": "Pacific/Auckland",
        "model": "gpt-test",
        "reasoning-effort": "medium",
    }
    workflow(workspace, "{}")
    assert local.workflow_settings(workspace) == {
        "timezone": "Europe/Amsterdam",
        "model": "",
        "reasoning-effort": "high",
    }


@pytest.mark.parametrize(
    "inputs,extra",
    [
        ("timezone: ${{ vars.TZ }}", ""),
        ("model: ${{ vars.MODEL }}", ""),
        ("reasoning-effort: 3", ""),
        ("timezone: missing/timezone", ""),
        ("timezone: UTC", "      - uses: vinkjoshua/daily-briefing@v1\n"),
        ("timezone: UTC", "      - uses: vinkjoshua/daily-briefing@${{ vars.VERSION }}\n"),
        ("timezone: UTC", "      - run: !!python/object/apply:os.system [echo nope]\n"),
    ],
)
def test_workflow_rejects_ambiguous_or_nonliteral_settings(workspace, inputs, extra):
    workflow(workspace, inputs, extra)
    with pytest.raises(local.LocalError, match="workflow|literal|timezone"):
        local.workflow_settings(workspace)


@pytest.mark.parametrize(
    "path",
    [
        "interests.md",
        "sections/10-research.md",
        "state/seen.md",
        "sections",
        "state",
        ".github",
        "preview.html",
    ],
)
def test_preview_rejects_symlinks(workspace, tmp_path, monkeypatch, capsys, path):
    import shutil

    p = workspace / path
    outside = tmp_path / "outside"
    if p.is_dir():
        shutil.copytree(p, outside)
        shutil.rmtree(p)
    else:
        outside.write_text("outside unchanged")
        p.unlink(missing_ok=True)
    p.symlink_to(outside)
    monkeypatch.setattr(local, "ensure_tool", lambda tool: pytest.fail("must reject before Codex"))
    assert local.try_briefing(workspace) == 1
    assert "symlink" in capsys.readouterr().out


@pytest.mark.parametrize(
    "output,want",
    [("401 Unauthorized", "/fake/codex login"), ("service unavailable", "unavailable")],
)
def test_preview_auth_vs_outage(workspace, monkeypatch, tmp_path, capsys, output, want):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))

    class Fake:
        def __init__(self, *args):
            pass

        def probe(self):
            return CodexResult(1, output)

    monkeypatch.setattr(local, "Codex", Fake)
    assert local.try_briefing(workspace) == 1
    assert want in capsys.readouterr().out
    assert not (workspace / "preview.html").exists()


def test_try_cli_and_open(workspace, monkeypatch, tmp_path):
    monkeypatch.chdir(workspace)
    received = []
    monkeypatch.setattr(local, "try_briefing", lambda root, **kw: received.append((root, kw)) or 0)
    assert cli.main(["try", "--section", "10-research", "--open"]) == 0
    assert received == [(workspace, {"section": "10-research", "open_browser": True})]


def test_preview_copies_custom_state_but_no_agent_instructions(workspace, monkeypatch, tmp_path):
    (workspace / "state" / "custom").mkdir()
    (workspace / "state" / "custom" / "events.md").write_text("# Saved events\n")
    for name in ["AGENTS.md", "AGENTS.override.md"]:
        (workspace / "state" / name).write_text("Ignored instruction")
    before = snapshot(workspace)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "auth"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))

    class Fake:
        def __init__(self, binary, home, workdir):
            self.root = workdir

        def probe(self):
            assert (self.root / "state" / "custom" / "events.md").read_text() == "# Saved events\n"
            assert not list(self.root.rglob("AGENTS*"))
            return CodexResult(0, "OK")

        def exec(self, prompt, *, out_path, **kwargs):
            out_path.write_text("# Daily briefing — Preview\n\n## Research\nEvents\n")
            return CodexResult(0, "")

    monkeypatch.setattr(local, "Codex", Fake)
    assert local.try_briefing(workspace) == 0
    after = snapshot(workspace)
    after.pop("preview.html")
    assert after == before


def test_workflow_rejects_duplicate_keys(workspace):
    workflow(workspace, "timezone: UTC\n          timezone: Pacific/Auckland")
    with pytest.raises(local.LocalError, match="workflow|literal"):
        local.workflow_settings(workspace)


@pytest.mark.parametrize("mode", ["generation-failure", "empty", "symlink"])
def test_preview_failure_preserves_existing_html(workspace, monkeypatch, tmp_path, mode):
    (workspace / "preview.html").write_text("existing preview")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "auth"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))
    before = snapshot(workspace)
    outside = tmp_path / "outside.md"
    outside.write_text("outside stays untouched")

    class Fake:
        def __init__(self, *args):
            pass

        def probe(self):
            return CodexResult(0, "OK")

        def exec(self, prompt, *, out_path, **kwargs):
            if mode == "symlink":
                out_path.symlink_to(outside)
            else:
                out_path.write_text("")
            return CodexResult(1 if mode == "generation-failure" else 0, "")

    monkeypatch.setattr(local, "Codex", Fake)
    assert local.try_briefing(workspace) == 1
    assert snapshot(workspace) == before
    assert outside.read_text() == "outside stays untouched"


def test_preview_opens_browser_only_after_success(workspace, monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "auth"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))
    opened = []

    class Fake:
        def __init__(self, *args):
            pass

        def probe(self):
            return CodexResult(0, "OK")

        def exec(self, prompt, *, out_path, **kwargs):
            out_path.write_text("# Daily briefing — Preview\n\n## Research\nHello\n")
            return CodexResult(0, "")

    def open_html(url):
        assert "Hello" in (workspace / "preview.html").read_text()
        opened.append(url)

    monkeypatch.setattr(local, "Codex", Fake)
    monkeypatch.setattr(local.webbrowser, "open", open_html)
    assert local.try_briefing(workspace, open_browser=True) == 0
    assert opened == [(workspace / "preview.html").as_uri()]


def test_preview_refuses_auth_home_in_source(workspace, monkeypatch, capsys):
    monkeypatch.setenv("CODEX_HOME", str(workspace / "auth"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: pytest.fail("should not run"))
    assert local.try_briefing(workspace) == 1
    assert "CODEX_HOME must be outside" in capsys.readouterr().out


def test_custom_state_does_not_copy_credentials_or_archives(workspace, monkeypatch, tmp_path):
    for name in [
        ".codex/auth.json",
        ".briefing/codex-auth.enc",
        ".git/config",
        "archives/old.md",
        "briefings/old.md",
        "auth.json",
        ".env",
    ]:
        p = workspace / "state" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("test-only-sensitive-file")
    before = snapshot(workspace)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "auth"))
    monkeypatch.setattr(local, "ensure_tool", lambda tool: Path("/fake/codex"))

    class Fake:
        def __init__(self, binary, home, workdir):
            self.root = workdir

        def probe(self):
            assert sorted(
                str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()
            ) == [
                "interests.md",
                "sections/10-research.md",
                "sections/20-news.md",
                "state/seen.md",
                "state/watchlist.md",
            ]
            return CodexResult(0, "OK")

        def exec(self, prompt, *, out_path, **kwargs):
            out_path.write_text("# Daily briefing — Preview\n\n## Research\nHello\n")
            return CodexResult(0, "")

    monkeypatch.setattr(local, "Codex", Fake)
    assert local.try_briefing(workspace) == 0
    after = snapshot(workspace)
    after.pop("preview.html")
    assert after == before


def test_try_real_git_repo_with_subprocess_wrapper(workspace, monkeypatch, tmp_path, fake_codex):
    import json
    import subprocess

    from daily_briefing.codex import Codex

    subprocess.run(["git", "init", "-b", "main", str(workspace)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(workspace), "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace),
            "-c",
            "maintenance.auto=false",
            "-c",
            "gc.auto=0",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=t@x",
            "commit",
            "-m",
            "fixture",
        ],
        check=True,
        capture_output=True,
    )
    before = snapshot(workspace)
    home = tmp_path / "auth"
    home.mkdir()
    (home / "config.toml").write_text('cli_auth_credentials_store = "auto"\n')
    log = tmp_path / "codex-calls.jsonl"
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("SMTP_PASSWORD", "test-only-secret")
    monkeypatch.setattr(local, "ensure_tool", lambda tool: fake_codex)
    monkeypatch.setattr(
        local,
        "Codex",
        lambda binary, auth, workdir: Codex(
            binary, auth, workdir, extra_env={"FAKE_CODEX_EXEC": "ok", "FAKE_CODEX_LOG": str(log)}
        ),
    )
    monkeypatch.chdir(workspace)
    assert cli.main(["try", "--section", "10-research"]) == 0
    after = snapshot(workspace)
    after.pop("preview.html")
    assert after == before
    assert "Hello" in (workspace / "preview.html").read_text()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 2
    for call, search in zip(calls, ['web_search="disabled"', 'web_search="live"'], strict=True):
        assert "SMTP_PASSWORD" not in call["env"]
        assert "--ignore-user-config" in call["args"]
        assert "--ignore-rules" in call["args"]
        assert "project_doc_max_bytes=0" in call["args"]
        assert 'cli_auth_credentials_store="auto"' in call["args"]
        assert search in call["args"]
        assert call["args"][call["args"].index("-C") + 1] != str(workspace)
