"""Run the Codex CLI as a subprocess with a sanitised environment."""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import threading
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from daily_briefing.auth import parse_device_prompt

ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "USER")


@dataclass(frozen=True)
class CodexResult:
    """Outcome of a Codex invocation."""

    returncode: int
    output: str

    @property
    def ok(self) -> bool:
        """Whether Codex exited successfully."""
        return self.returncode == 0


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """Stop a process and everything it spawned: SIGTERM, then SIGKILL after 10 s.

    Args:
        proc: A process started with start_new_session=True.
    """
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=10)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


class Codex:
    """Thin wrapper around the codex executable."""

    def __init__(
        self,
        binary: str,
        codex_home: Path,
        workdir: Path,
        base_env: Mapping[str, str] | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> None:
        """Create a wrapper.

        Args:
            binary: Path or name of the codex executable.
            codex_home: CODEX_HOME for every call.
            workdir: Directory Codex works in (-C).
            base_env: Environment to filter; defaults to os.environ.
            extra_env: Added verbatim after filtering (tests only).
        """
        self.binary = binary
        self.codex_home = codex_home
        self.workdir = workdir
        self._base_env = dict(os.environ if base_env is None else base_env)
        self._extra_env = dict(extra_env or {})

    def child_env(self) -> dict[str, str]:
        """Return the environment for Codex: an allowlist, so secrets never reach it.

        Returns:
            Environment variables for the subprocess.
        """
        env = {k: v for k, v in self._base_env.items() if k in ENV_ALLOWLIST}
        env["CODEX_HOME"] = str(self.codex_home)
        env.update(self._extra_env)
        return env

    def exec(
        self,
        prompt: str,
        *,
        out_path: Path | None = None,
        sandbox: str = "workspace-write",
        effort: str = "high",
        model: str = "",
        web_search: bool = True,
        timeout: float = 2100,
    ) -> CodexResult:
        """Run `codex exec` with the prompt on stdin.

        Args:
            prompt: Prompt text.
            out_path: Where Codex writes its final message (-o).
            sandbox: Codex sandbox mode.
            effort: Reasoning effort.
            model: Optional model override.
            web_search: Enable live web search.
            timeout: Seconds before the process is killed.

        Returns:
            Exit code and combined output; 124 on timeout.
        """
        self.codex_home.mkdir(parents=True, exist_ok=True)
        args = [
            self.binary,
            "exec",
            "-",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "-c",
            "project_doc_max_bytes=0",
            "-c",
            'web_search="live"' if web_search else 'web_search="disabled"',
            "-C",
            str(self.workdir),
            "-s",
            sandbox,
            "-c",
            "model_reasoning_effort=" + json.dumps(effort),
        ]
        config = self.codex_home / "config.toml"
        if config.is_file():
            try:
                store = tomllib.loads(config.read_text(encoding="utf-8")).get(
                    "cli_auth_credentials_store", "file"
                )
            except tomllib.TOMLDecodeError as exc:
                raise ValueError(
                    "Cannot read Codex credential-store setting: invalid config.toml"
                ) from exc
            if not isinstance(store, str) or store not in {"file", "keyring", "auto", "ephemeral"}:
                raise ValueError("Unsupported Codex credential-store setting in config.toml")
            args += ["-c", "cli_auth_credentials_store=" + json.dumps(store)]
        if model:
            args += ["-m", model]
        if out_path is not None:
            args += ["-o", str(out_path)]
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.child_env(),
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(input=prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            stdout, stderr = proc.communicate()
            output = _text(stdout) + _text(stderr)
            return CodexResult(124, output + f"\ncodex timed out after {timeout:.0f}s")
        except BaseException:
            _kill_group(proc)
            proc.communicate()
            raise
        return CodexResult(proc.returncode, stdout + stderr)

    def probe(self) -> CodexResult:
        """Make a tiny call that validates (and if stale, refreshes) the login.

        Returns:
            The result of a minimal read-only, low-effort exec.
        """
        return self.exec(
            "Reply with the single word OK.",
            sandbox="read-only",
            effort="low",
            web_search=False,
            timeout=300,
        )

    def device_login(
        self, on_prompt: Callable[[str, str], None], timeout: float = 960
    ) -> CodexResult:
        """Run `codex login --device-auth` and wait for the user to approve.

        Args:
            on_prompt: Called once with (url, code) as soon as Codex prints them.
            timeout: Seconds before the login process is killed.

        Returns:
            Exit code and combined output; 124 on timeout.
        """
        self.codex_home.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(
            [self.binary, "login", "--device-auth"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=self.child_env(),
            start_new_session=True,
        )
        expired = threading.Event()

        def expire() -> None:
            expired.set()
            _kill_group(proc)

        watchdog = threading.Timer(timeout, expire)
        seen, announced = "", False
        try:
            watchdog.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                seen += line
                if not announced and (parsed := parse_device_prompt(seen)):
                    on_prompt(*parsed)
                    announced = True
            returncode = proc.wait()
            if expired.is_set():
                return CodexResult(124, seen + f"\ncodex login timed out after {timeout:.0f}s")
            return CodexResult(returncode, seen)
        except BaseException:
            _kill_group(proc)
            raise
        finally:
            watchdog.cancel()
            if watchdog.ident is not None:
                watchdog.join()
            if proc.stdout is not None:
                proc.stdout.close()
