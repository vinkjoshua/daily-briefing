"""Orchestrate one briefing run: guard, login, generate, send."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from daily_briefing.auth import device_login_failure, is_auth_error
from daily_briefing.codex import CodexResult
from daily_briefing.config import Config
from daily_briefing.login_store import restore_login
from daily_briefing.notices import (
    NOTICE_ICONS,
    device_code_notice,
    failure_notice,
    reconnect_notice,
)
from daily_briefing.prompt import build_prompt
from daily_briefing.sections import load_sections
from daily_briefing.state import Paths, already_sent, mark_notified, today_in, was_notified


class CodexLike(Protocol):
    """The parts of Codex the runner uses."""

    def probe(self) -> CodexResult:
        """Validate the login."""
        ...

    def device_login(
        self, on_prompt: Callable[[str, str], None], timeout: float = 960
    ) -> CodexResult:
        """Run the device-code login."""
        ...

    def exec(self, prompt: str, *, out_path: Path | None = None, **kwargs: object) -> CodexResult:
        """Run a prompt."""
        ...


class RunError(Exception):
    """A run failed in a way the user should hear about."""


@dataclass
class Deps:
    """Collaborators injected into run()."""

    codex: CodexLike
    send: Callable[[str, Mapping[str, str]], None]
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    log: Callable[[str], None] = field(default=lambda message: print(message, flush=True))


def _tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def run(cfg: Config, deps: Deps) -> int:
    """Run one briefing.

    Args:
        cfg: Configuration.
        deps: Injected collaborators.

    Returns:
        0 when sent or deliberately skipped, 1 on failure, 2 when refused (public repo).
    """
    if cfg.repo_public:
        deps.log(
            "::error::This repository is public. Make it private: your Codex login is stored in it."
        )
        return 2
    paths = Paths(cfg.workspace)
    day = today_in(cfg.timezone, deps.now())
    if already_sent(paths, day) and not cfg.force:
        deps.log(f"Briefing for {day} already sent; nothing to do.")
        return 0
    try:
        sections = load_sections(paths.sections_dir)
        if (
            not restore_login(paths.auth_blob, cfg.codex_home, cfg.auth_key)
            and paths.auth_blob.is_file()
        ):
            deps.log("::warning::Could not decrypt the saved login (BRIEFING_KEY changed?).")
        probe = deps.codex.probe()
        if not probe.ok:
            if not is_auth_error(probe.output):
                raise RunError("Codex is unavailable:\n" + _tail(probe.output))
            if cfg.event_name != "workflow_dispatch":
                if not was_notified(paths, day, "reconnect"):
                    deps.send(reconnect_notice(cfg.workflow_url), NOTICE_ICONS)
                    mark_notified(paths, day, "reconnect")
                deps.log("::warning::Codex login needed; reconnect email sent.")
                return 0

            def announce(url: str, code: str) -> None:
                deps.log(f"::notice title=Approve your login::Open {url} and enter {code}")
                deps.send(device_code_notice(url, code), NOTICE_ICONS)

            login = deps.codex.device_login(announce)
            if not login.ok:
                raise RunError(device_login_failure(login.output, login.returncode))
        draft = paths.draft(day)
        draft.parent.mkdir(parents=True, exist_ok=True)
        result = deps.codex.exec(
            build_prompt(day, sections), out_path=draft, effort=cfg.effort, model=cfg.model
        )
        if not result.ok:
            raise RunError("Codex failed:\n" + _tail(result.output))
        body = draft.read_text(encoding="utf-8") if draft.is_file() else ""
        if not body.strip():
            raise RunError("Codex returned an empty briefing.")
        deps.send(body, {s.title: s.icon for s in sections})
        draft.replace(paths.briefing(day))
        deps.log(f"Briefing for {day} sent.")
        return 0
    except Exception as exc:  # noqa: BLE001 - every failure must reach the user
        deps.log(f"::error::{exc}")
        if not was_notified(paths, day, "failure"):
            try:
                deps.send(failure_notice(str(exc), cfg.run_url), NOTICE_ICONS)
                mark_notified(paths, day, "failure")
            except Exception as mail_exc:  # noqa: BLE001
                deps.log(f"::error::Could not send the failure email: {mail_exc}")
        return 1
