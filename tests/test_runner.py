from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from daily_briefing.codex import CodexResult
from daily_briefing.config import Config
from daily_briefing.runner import Deps, run
from daily_briefing.state import Paths, mark_notified
from daily_briefing.vault import encrypt

KEY = "k" * 32
DAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)
UNAUTHORIZED = "ERROR: unexpected status 401 Unauthorized"


class FakeCodex:
    def __init__(
        self,
        *,
        logged_in=True,
        device_ok=True,
        exec_ok=True,
        probe_output="",
        reply="# Daily briefing — Test\n\n## Research\nHello\n",
    ):
        self.logged_in, self.device_ok, self.exec_ok = logged_in, device_ok, exec_ok
        self.probe_output, self.reply = probe_output, reply
        self.calls: list[str] = []
        self.prompt = ""

    def probe(self):
        self.calls.append("probe")
        if self.probe_output:
            return CodexResult(1, self.probe_output)
        return CodexResult(0, "OK") if self.logged_in else CodexResult(1, UNAUTHORIZED)

    def device_login(self, on_prompt, timeout=960):
        self.calls.append("device_login")
        on_prompt("https://auth.openai.com/codex/device", "ABCD-12345")
        self.logged_in = self.device_ok
        return self.device_ok

    def exec(self, prompt, *, out_path=None, **kwargs):
        self.calls.append("exec")
        self.prompt = prompt
        if not self.exec_ok:
            return CodexResult(1, "ERROR: stream disconnected")
        if out_path is not None:
            out_path.write_text(self.reply, encoding="utf-8")
        return CodexResult(0, "done")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "sections").mkdir()
    (tmp_path / "sections" / "10-research.md").write_text(
        "---\ntitle: Research\nicon: 🧠\n---\nMax 3 papers.\n", encoding="utf-8"
    )
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "seen.md").write_text("# Seen\n", encoding="utf-8")
    (tmp_path / "interests.md").write_text("# Interests\n", encoding="utf-8")
    return tmp_path


def config(workspace: Path, **overrides: str) -> Config:
    env = {
        "SMTP_USER": "me@example.com",
        "SMTP_PASSWORD": "pw",
        "BRIEFING_KEY": KEY,
        "GITHUB_WORKSPACE": str(workspace),
        "CODEX_HOME": str(workspace / ".codex-home"),
        "GITHUB_EVENT_NAME": "schedule",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_REPOSITORY": "ann/b",
        "GITHUB_WORKFLOW_REF": "ann/b/.github/workflows/briefing.yml@refs/heads/main",
        "GITHUB_RUN_ID": "7",
    }
    env.update(overrides)
    return Config.from_env(env)


def harness(codex):
    sent: list[tuple[str, dict[str, str]]] = []
    logs: list[str] = []
    deps = Deps(
        codex=codex,
        send=lambda md, icons: sent.append((md, dict(icons))),
        now=lambda: NOW,
        log=logs.append,
    )
    return deps, sent, logs


def test_happy_path_sends_and_archives(workspace):
    codex = FakeCodex()
    deps, sent, _ = harness(codex)
    assert run(config(workspace), deps) == 0
    assert codex.calls == ["probe", "exec"]
    assert "Today is 2026-10-07." in codex.prompt and "Max 3 papers." in codex.prompt
    assert sent == [("# Daily briefing — Test\n\n## Research\nHello\n", {"Research": "🧠"})]
    paths = Paths(workspace)
    assert paths.briefing(DAY).read_text().startswith("# Daily briefing")
    assert not paths.draft(DAY).exists()


def test_public_repo_refused(workspace):
    codex = FakeCodex()
    deps, sent, logs = harness(codex)
    assert run(config(workspace, REPO_PRIVATE="false"), deps) == 2
    assert codex.calls == [] and sent == []
    assert any("private" in line for line in logs)


def test_already_sent_skips(workspace):
    Paths(workspace).briefing(DAY).parent.mkdir()
    Paths(workspace).briefing(DAY).write_text("# done")
    codex = FakeCodex()
    deps, sent, _ = harness(codex)
    assert run(config(workspace), deps) == 0
    assert codex.calls == [] and sent == []


def test_force_runs_again(workspace):
    Paths(workspace).briefing(DAY).parent.mkdir()
    Paths(workspace).briefing(DAY).write_text("# done")
    deps, sent, _ = harness(FakeCodex())
    assert run(config(workspace, BRIEFING_FORCE="true"), deps) == 0
    assert len(sent) == 1


def test_schedule_auth_failure_sends_one_reconnect_per_day(workspace):
    deps1, sent1, _ = harness(FakeCodex(logged_in=False))
    assert run(config(workspace), deps1) == 0
    deps2, sent2, _ = harness(FakeCodex(logged_in=False))
    assert run(config(workspace), deps2) == 0
    assert len(sent1) == 1 and sent2 == []
    assert "reconnect needed" in sent1[0][0]
    assert "actions/workflows/briefing.yml" in sent1[0][0]


def test_schedule_never_starts_device_login(workspace):
    codex = FakeCodex(logged_in=False)
    deps, _, _ = harness(codex)
    run(config(workspace), deps)
    assert "device_login" not in codex.calls


def test_dispatch_auth_failure_runs_device_login_then_briefing(workspace):
    codex = FakeCodex(logged_in=False)
    deps, sent, logs = harness(codex)
    assert run(config(workspace, GITHUB_EVENT_NAME="workflow_dispatch"), deps) == 0
    assert codex.calls == ["probe", "device_login", "exec"]
    assert "ABCD-12345" in sent[0][0]
    assert sent[1][0].startswith("# Daily briefing — Test")
    assert any("::notice" in line and "ABCD-12345" in line for line in logs)


def test_dispatch_device_login_expired(workspace):
    codex = FakeCodex(logged_in=False, device_ok=False)
    deps, sent, _ = harness(codex)
    assert run(config(workspace, GITHUB_EVENT_NAME="workflow_dispatch"), deps) == 1
    assert "exec" not in codex.calls
    assert "run failed" in sent[-1][0] and "Run workflow again" in sent[-1][0]


def test_probe_other_failure_is_reported(workspace):
    codex = FakeCodex(probe_output="ERROR: unexpected status 429 Too Many Requests")
    deps, sent, _ = harness(codex)
    assert run(config(workspace), deps) == 1
    assert "exec" not in codex.calls
    assert "429" in sent[0][0]


def test_exec_failure_emails_once_per_day(workspace):
    deps, sent, _ = harness(FakeCodex(exec_ok=False))
    assert run(config(workspace), deps) == 1
    deps2, sent2, _ = harness(FakeCodex(exec_ok=False))
    assert run(config(workspace), deps2) == 1
    assert len(sent) == 1 and sent2 == []
    assert "run failed" in sent[0][0]


def test_empty_output_is_failure(workspace):
    deps, sent, _ = harness(FakeCodex(reply="   "))
    assert run(config(workspace), deps) == 1
    assert not Paths(workspace).briefing(DAY).exists()
    assert "empty" in sent[0][0]


def test_undecryptable_login_triggers_reconnect(workspace):
    blob = Paths(workspace).auth_blob
    blob.parent.mkdir()
    blob.write_bytes(encrypt(b'{"valid": true}', "other-key-" + "x" * 30))
    codex = FakeCodex(logged_in=False)
    deps, sent, logs = harness(codex)
    assert run(config(workspace), deps) == 0
    assert "reconnect needed" in sent[0][0]
    assert any("decrypt" in line for line in logs)


def test_restored_login_lands_in_codex_home(workspace):
    blob = Paths(workspace).auth_blob
    blob.parent.mkdir()
    blob.write_bytes(encrypt(b'{"valid": true}', KEY))
    deps, _, _ = harness(FakeCodex())
    run(config(workspace), deps)
    assert (workspace / ".codex-home" / "auth.json").read_bytes() == b'{"valid": true}'


def test_missing_sections_reported(workspace):
    for f in (workspace / "sections").iterdir():
        f.unlink()
    deps, sent, _ = harness(FakeCodex())
    assert run(config(workspace), deps) == 1
    assert "No section files" in sent[0][0]


def test_failure_email_error_does_not_raise(workspace):
    def broken_send(md, icons):
        raise OSError("smtp down")

    deps = Deps(
        codex=FakeCodex(exec_ok=False),
        send=broken_send,
        now=lambda: NOW,
        log=lambda s: None,
    )
    assert run(config(workspace), deps) == 1


def test_already_notified_failure_not_resent(workspace):
    mark_notified(Paths(workspace), DAY, "failure")
    deps, sent, _ = harness(FakeCodex(exec_ok=False))
    assert run(config(workspace), deps) == 1
    assert sent == []


def test_corrupt_notified_file_does_not_crash(workspace):
    paths = Paths(workspace)
    paths.notified_file.parent.mkdir(parents=True, exist_ok=True)
    paths.notified_file.write_bytes(b"[]")
    deps, sent, _ = harness(FakeCodex(exec_ok=False))
    assert run(config(workspace), deps) == 1
    assert len(sent) == 1
    assert "run failed" in sent[0][0]
