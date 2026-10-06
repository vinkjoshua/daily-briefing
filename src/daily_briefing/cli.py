"""Command-line entry point used by action.yml (and handy locally)."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from daily_briefing import mailer, setup
from daily_briefing.codex import Codex
from daily_briefing.config import Config, ConfigError
from daily_briefing.login_store import save_login_if_changed
from daily_briefing.persist import ALLOWLIST, PersistError, authenticated_url, commit_and_push
from daily_briefing.render import parse_briefing, render_html
from daily_briefing.runner import Deps, run
from daily_briefing.sections import SectionError, load_sections
from daily_briefing.state import Paths, already_sent, today_in


def make_sender(cfg: Config) -> Callable[[str, Mapping[str, str]], None]:
    """Build the function that renders and emails a Markdown briefing.

    Args:
        cfg: Configuration with SMTP settings.

    Returns:
        send(markdown, icons).
    """
    settings = mailer.SmtpSettings(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user, cfg.smtp_password)

    def send(markdown: str, icons: Mapping[str, str]) -> None:
        briefing = parse_briefing(markdown, icons)
        generated = f"{datetime.now(ZoneInfo(cfg.timezone)):%a %d %b %Y, %H:%M}"
        html = render_html(briefing, repo_url=cfg.repo_url, generated=generated)
        message = mailer.build_message(
            subject=briefing.subject,
            text=briefing.markdown,
            html=html,
            sender=cfg.smtp_user,
            to=cfg.mail_to,
        )
        mailer.send(message, settings)

    return send


def _guard(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    cfg = Config.from_env(env, require_secrets=False)
    day = today_in(cfg.timezone)
    unconfigured = env.get("HAS_AUTH_KEY") == "false"
    if unconfigured:
        print(
            "::notice::Add the SMTP_USER, SMTP_PASSWORD and BRIEFING_KEY secrets"
            " to start your briefing."
        )
    skip = unconfigured or (already_sent(Paths(cfg.workspace), day) and not cfg.force)
    line = f"skip={'true' if skip else 'false'}"
    print(f"{day}: {line}")
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return 0


def _run(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    cfg = Config.from_env(env)
    codex = Codex(cfg.codex_bin, cfg.codex_home, cfg.workspace, base_env=env)
    return run(cfg, Deps(codex=codex, send=make_sender(cfg)))


def _persist(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    cfg = Config.from_env(env, require_secrets=False)
    paths = Paths(cfg.workspace)
    if cfg.auth_key and save_login_if_changed(paths.auth_blob, cfg.codex_home, cfg.auth_key):
        print("Saved refreshed Codex login.")
    token = env.get("GITHUB_TOKEN", "")
    repository = env.get("GITHUB_REPOSITORY", "")
    remote = (
        authenticated_url(env.get("GITHUB_SERVER_URL", "https://github.com"), repository, token)
        if token and repository
        else "origin"
    )
    branch = env.get("GITHUB_REF_NAME") or "main"
    # A failed run must not commit Codex's edits to state/; .briefing/ (login) still goes.
    sent = already_sent(paths, today_in(cfg.timezone))
    include = ALLOWLIST if sent else ("briefings", ".briefing")
    try:
        pushed = commit_and_push(
            cfg.workspace,
            f"chore: daily briefing {today_in(cfg.timezone)}",
            branch=branch,
            remote=remote,
            token=token,
            include=include,
        )
    except PersistError as exc:
        print(f"::error::{exc}")
        return 1
    print("State pushed." if pushed else "No state changes.")
    return 0


def _validate(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    root = Path(args.dir)
    try:
        sections = load_sections(root / "sections")
    except SectionError as exc:
        print(f"Problem: {exc}")
        return 1
    if not (root / "interests.md").is_file():
        print("Problem: interests.md is missing.")
        return 1
    count = len(sections)
    print(
        f"OK: {count} section{'s' if count != 1 else ''}: " + ", ".join(s.title for s in sections)
    )
    return 0


def _preview(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    icons = {s.title: s.icon for s in load_sections(args.sections)} if args.sections else {}
    briefing = parse_briefing(Path(args.markdown).read_text(encoding="utf-8"), icons)
    Path(args.output).write_text(render_html(briefing, generated="preview"), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


def _init(args: argparse.Namespace, env: Mapping[str, str]) -> int:
    return setup.initialize(Path(args.directory))


COMMANDS: dict[str, Callable[[argparse.Namespace, Mapping[str, str]], int]] = {
    "init": _init,
    "guard": _guard,
    "run": _run,
    "persist": _persist,
    "validate": _validate,
    "preview": _preview,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run a subcommand.

    Args:
        argv: Arguments without the program name; defaults to sys.argv[1:].

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="daily-briefing")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Set up a personal daily briefing")
    init.add_argument("directory", nargs="?", default="my-briefing")
    sub.add_parser("guard", help="Write skip=true|false to $GITHUB_OUTPUT")
    sub.add_parser("run", help="Generate and email today's briefing")
    sub.add_parser("persist", help="Save the login and commit state")
    validate = sub.add_parser("validate", help="Check sections/ and interests.md")
    validate.add_argument("--dir", default=".")
    preview = sub.add_parser("preview", help="Render a Markdown briefing to HTML")
    preview.add_argument("markdown")
    preview.add_argument("--sections", type=Path)
    preview.add_argument("-o", "--output", default="preview.html")
    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args, os.environ)
    except setup.SetupCancelled as exc:
        print(f"Setup cancelled. Resume with daily-briefing init {shlex.quote(str(exc.directory))}")
        return 130
    except ConfigError as exc:
        print(f"::error::{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
