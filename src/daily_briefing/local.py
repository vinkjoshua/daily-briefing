"""Generate a local preview without changing the instance or its retained state."""

from __future__ import annotations

import os
import shlex
import shutil
import tempfile
import webbrowser
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from daily_briefing.auth import is_auth_error
from daily_briefing.bootstrap import BootstrapError, ensure_tool
from daily_briefing.codex import Codex
from daily_briefing.prompt import build_prompt
from daily_briefing.render import parse_briefing, render_html
from daily_briefing.sections import SectionError, load_sections
from daily_briefing.state import today_in


class LocalError(Exception):
    """An instance cannot be previewed safely."""


def _check_path(root: Path, path: Path, *, directory: bool = False) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise LocalError(f"Refusing symlink: {item}")
        if item == root:
            break
    if not (path.is_dir() if directory else path.is_file()):
        raise LocalError(f"Expected a regular {'directory' if directory else 'file'}: {path}")


class _WorkflowLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        keys = [self.construct_object(key, deep=deep) for key, _ in node.value]
        if len(keys) != len(set(keys)):
            raise ValueError("Ambiguous workflow: duplicate mapping keys")
        return super().construct_mapping(node, deep=deep)


def workflow_settings(root: Path) -> dict[str, str]:
    """Read literal preview settings from exactly one recognized action step.

    Args:
        root: Instance directory containing .github/workflows/briefing.yml.

    Returns:
        timezone, model and reasoning-effort, including existing action defaults.

    Raises:
        LocalError: For unsafe paths, ambiguous workflows or nonliteral settings.
    """
    path = root / ".github" / "workflows" / "briefing.yml"
    _check_path(root, path)
    guidance = (
        "Use one daily-briefing action with literal settings in .github/workflows/briefing.yml."
    )
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=_WorkflowLoader)
        jobs = document["jobs"]
        if not isinstance(jobs, dict):
            raise ValueError
        matches = []
        for job in jobs.values():
            if not isinstance(job, dict) or not isinstance(job.get("steps", []), list):
                raise ValueError
            for step in job.get("steps", []):
                if not isinstance(step, dict):
                    raise ValueError
                uses = step.get("uses", "")
                if isinstance(uses, str) and uses.startswith("vinkjoshua/daily-briefing@"):
                    if "${{" in uses or not uses.split("@", 1)[1].strip():
                        raise ValueError
                    matches.append(step)
        if len(matches) != 1:
            raise ValueError
        inputs = matches[0].get("with", {})
        if not isinstance(inputs, dict):
            raise ValueError
        settings = {"timezone": "Europe/Amsterdam", "model": "", "reasoning-effort": "high"}
        for key, default in settings.items():
            value = inputs.get(key, default)
            if not isinstance(value, str) or "${{" in value:
                raise ValueError
            settings[key] = value
        if settings["reasoning-effort"] not in {
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
        }:
            raise ValueError
        ZoneInfo(settings["timezone"])
    except ZoneInfoNotFoundError as exc:
        raise LocalError("Invalid workflow timezone. Use a literal IANA timezone.") from exc
    except (yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
        raise LocalError(guidance) from exc
    return settings


def _copy_inputs(root: Path, target: Path, section: str | None) -> None:
    _check_path(root, root, directory=True)
    _check_path(root, root / "interests.md")
    _check_path(root, root / "sections", directory=True)
    files = sorted((root / "sections").glob("*.md"))
    if section is not None:
        files = [path for path in files if path.stem == section]
        if not files:
            raise LocalError(f"Unknown section {section!r}; use a section filename without .md.")
    (target / "sections").mkdir()
    for path in files:
        _check_path(root, path)
        shutil.copyfile(path, target / "sections" / path.name)
    shutil.copyfile(root / "interests.md", target / "interests.md")
    _check_path(root, root / "state", directory=True)
    (target / "state").mkdir()
    for path in sorted((root / "state").rglob("*")):
        directory = path.is_dir()
        _check_path(root, path, directory=directory)
        if any(
            part in {".git", ".briefing", ".codex", ".agents", "archives", "briefings"}
            for part in path.relative_to(root).parts
        ):
            continue
        if path.name in {
            "AGENTS.md",
            "AGENTS.override.md",
            "CLAUDE.md",
            "GEMINI.md",
            "auth.json",
            "codex-auth.enc",
            ".env",
        }:
            continue
        destination = target / path.relative_to(root)
        if directory:
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def try_briefing(root: Path, *, section: str | None = None, open_browser: bool = False) -> int:
    """Generate preview.html using the user's local Codex login in an isolated workspace.

    Args:
        root: Instance directory, never modified except for preview.html.
        section: Optional section filename stem.
        open_browser: Open the HTML after a successful atomic write.

    Returns:
        Zero on success, one with actionable guidance on failure.
    """
    try:
        root = root.absolute()
        output = root / "preview.html"
        if output.exists() or output.is_symlink():
            _check_path(root, output)
        settings = workflow_settings(root)
        home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").expanduser().absolute()
        if home.resolve().is_relative_to(root.resolve()):
            raise LocalError(
                "CODEX_HOME must be outside this instance. Use your existing ~/.codex login."
            )
        with tempfile.TemporaryDirectory(prefix="briefing-preview-") as directory:
            workdir = Path(directory)
            _copy_inputs(root, workdir, section)
            sections = load_sections(workdir / "sections")
            binary = ensure_tool("codex")
            login_hint = (
                f"Local Codex login needed. Run {shlex.quote(str(binary))} login locally "
                "for browser login, then try again."
            )
            codex = Codex(str(binary), home, workdir)
            probe = codex.probe()
            if not probe.ok:
                if is_auth_error(probe.output):
                    raise LocalError(login_hint)
                raise LocalError(
                    f"Codex is unavailable (exit {probe.returncode}). Try again later."
                )
            draft = workdir / "draft.md"
            result = codex.exec(
                build_prompt(today_in(settings["timezone"]), sections),
                out_path=draft,
                effort=settings["reasoning-effort"],
                model=settings["model"],
            )
            if not result.ok:
                if is_auth_error(result.output):
                    raise LocalError(login_hint)
                raise LocalError(
                    f"Codex generation failed (exit {result.returncode}). Try again later."
                )
            _check_path(workdir, draft)
            markdown = draft.read_text(encoding="utf-8")
            if not markdown.strip():
                raise LocalError("Codex returned an empty briefing.")
            html = render_html(
                parse_briefing(markdown, {s.title: s.icon for s in sections}), generated="preview"
            )
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as fh:
            temporary = Path(fh.name)
            try:
                fh.write(html)
                fh.flush()
                if output.exists() or output.is_symlink():
                    _check_path(root, output)
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"Wrote {output}")
        if open_browser:
            webbrowser.open(output.as_uri())
        return 0
    except (LocalError, SectionError, BootstrapError, OSError, ValueError) as exc:
        print(f"Problem: {exc}")
        return 1
