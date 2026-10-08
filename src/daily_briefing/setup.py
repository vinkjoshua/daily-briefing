"""Create and publish a personal daily briefing with deterministic guided setup."""

from __future__ import annotations

import getpass
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import smtplib
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from daily_briefing import mailer
from daily_briefing.bootstrap import BootstrapError, ensure_tool
from daily_briefing.github import CommandError, git, run_gh
from daily_briefing.sections import SectionError, parse_section

STATE = "daily-briefing-init.json"
SECRET_NAMES = {"SMTP_USER", "SMTP_PASSWORD", "BRIEFING_KEY"}
PROVIDERS = {
    "gmail": ("smtp.gmail.com", 465),
    "icloud": ("smtp.mail.me.com", 587),
    "fastmail": ("smtp.fastmail.com", 465),
}
REPO_FIELDS = "nameWithOwner,id,isPrivate,owner,isEmpty"
INITIAL_FILES = (
    "interests.md",
    "README.md",
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "briefing",
    ".github/workflows/briefing.yml",
    "state/seen.md",
    "state/watchlist.md",
)


class SetupError(RuntimeError):
    """Setup stopped without changing existing accepted files or credentials."""


class SetupCancelled(KeyboardInterrupt):
    """Carry the accepted directory back to the CLI recovery message."""

    def __init__(self, directory: Path):
        """Remember the accepted recovery directory."""
        self.directory = directory


def _default_timezone() -> str:
    """Discover an IANA name from standard system files, falling back to UTC."""
    candidates = [os.environ.get("TZ", "")]
    try:
        localtime = str(Path("/etc/localtime").resolve())
        if "/zoneinfo/" in localtime:
            candidates.append(localtime.split("/zoneinfo/", 1)[1])
        if Path("/etc/timezone").is_file():
            candidates.append(Path("/etc/timezone").read_text().strip())
    except OSError:
        pass
    for candidate in candidates:
        try:
            ZoneInfo(candidate)
            return candidate
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return "UTC"


def _ask(prompt: str, default: str = "", valid=None, *, raw: bool = False) -> str:
    """Read and validate a nonsecret answer, reprompting invalid input."""
    while True:
        answer = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ")
        if not raw:
            answer = answer.strip()
        answer = answer or default
        if answer.strip() and (valid is None or valid(answer)):
            return answer
        print("Please enter a valid value.")


def _confirm(prompt: str) -> bool:
    """Require an explicit yes; a blank answer declines."""
    while True:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        if answer in ("", "n", "no", "y", "yes"):
            return answer in ("y", "yes")
        print("Please answer yes or no.")


def _safe_directory(root: Path) -> None:
    """Refuse links and existing directories that are unrelated to this setup."""
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise SetupError("Choose a directory without symlinks.")
    if root.exists() and not root.is_dir():
        raise SetupError("The setup path is not a directory.")
    if (root / ".git").exists() and not (root / ".git").is_dir():
        raise SetupError("Setup requires its own local Git repository.")
    if root.exists() and any(root.iterdir()) and not (root / ".git" / STATE).is_file():
        raise SetupError(
            "Directory is not empty and does not belong to this setup; choose another."
        )
    if root.exists() and any(path.is_symlink() for path in root.rglob("*")):
        raise SetupError("Setup files must not contain symlinks.")


def _save(root: Path, state: dict) -> None:
    """Atomically save only setup identity and progress inside Git's private directory."""
    temporary = root / ".git" / (STATE + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(root / ".git" / STATE)


def _starter():
    """Use packaged resources, or the canonical starter when running from source."""
    resource = files("daily_briefing").joinpath("starter")
    return resource if resource.is_dir() else Path(__file__).resolve().parents[2] / "template"


def _copy(source, destination: Path) -> None:
    """Copy starter resources without overwriting accepted local files."""
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            _copy(child, destination / child.name)
    elif not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _email(value: str) -> bool:
    """Reject malformed email headers and workflow expressions."""
    return bool(re.fullmatch(r"[^\s@<>\r\n{}]+@[^\s@<>\r\n{}]+\.[^\s@<>\r\n{}]+", value))


def _credentials(state: dict) -> mailer.SmtpSettings:
    """Test SMTP credentials in memory before any remote creation or publication."""
    while True:
        user = _ask("SMTP email/login", valid=_email)
        password = getpass.getpass("SMTP app password: ")
        if state["provider"] == "gmail":
            password = password.replace(" ", "")
        if not password:
            print("An app password is required.")
            continue
        recipient = input(f"Recipient (blank uses {user}): ").strip() or user
        if not _email(recipient):
            print("Please enter a valid recipient.")
            continue
        settings = mailer.SmtpSettings(state["host"], state["port"], user, password)
        message = mailer.build_message(
            subject="Daily briefing setup test",
            text="Your SMTP settings work. Continue setup in your terminal.",
            html="<p>Your SMTP settings work. Continue setup in your terminal.</p>",
            sender=user,
            to=recipient,
        )
        try:
            mailer.send(message, settings)
        except (OSError, smtplib.SMTPException):
            print("Test email failed. Check your provider's app password and SMTP settings.")
            continue
        if "recipient" in state and state["recipient"] != recipient:
            raise SetupError("Use the previously accepted recipient when resuming setup.")
        state["recipient"] = recipient
        print("Test email sent. SMTP credentials stay out of local files.")
        return settings


def _collect(root: Path, state: dict) -> None:
    """Save each accepted personalization answer and then prepare the starter files."""
    interests = root / "interests.md"
    for field, prompt, heading in (
        ("city", "Home city", "## About me\nHome city: "),
        (
            "research",
            "Professional and research interests",
            "## Professional and research interests\n",
        ),
        ("personal", "Personal interests and things you like to do", "## Things I like to do\n"),
    ):
        if not state.get(field):
            answer = _ask(prompt, raw=True)
            with interests.open("a", encoding="utf-8") as output:
                if field == "city" and interests.stat().st_size == 0:
                    output.write("# Interests\n\n")
                output.write(heading + answer + "\n\n")
            state[field] = True
            _save(root, state)
    starter = _starter()
    choices = sorted(starter.joinpath("sections").iterdir(), key=lambda path: path.name)
    if "sections" not in state:
        print("Choose one or more sections:")
        for index, source in enumerate(choices, 1):
            title = next(
                line[7:] for line in source.read_text().splitlines() if line.startswith("title: ")
            )
            print(f"  {index}. {title}")
        selection = _ask(
            "Section numbers, comma separated",
            valid=lambda value: all(
                part.strip() in {"1", "2", "3", "4", "5"} for part in value.split(",")
            ),
        )
        state["sections"] = [
            choices[index - 1].name
            for index in sorted({int(part.strip()) for part in selection.split(",")})
        ]
        for name in state["sections"]:
            _copy(starter.joinpath("sections", name), root / "sections" / name)
        _save(root, state)
    if "timezone" not in state:

        def timezone_valid(value):
            try:
                ZoneInfo(value)
                return True
            except (ValueError, ZoneInfoNotFoundError):
                return False

        state["timezone"] = _ask("Confirm IANA timezone", _default_timezone(), timezone_valid)
        _save(root, state)
    if "start" not in state:
        state["start"] = _ask(
            "First daily briefing time (HH:MM)",
            "07:00",
            lambda value: bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)),
        )
        _save(root, state)
    for name in ("README.md", ".gitignore", "state", "AGENTS.md", "CLAUDE.md", "briefing"):
        _copy(starter.joinpath(name), root / name)
    (root / "briefing").chmod(0o755)
    workflow = root / ".github/workflows/briefing.yml"
    if not workflow.exists():
        text = starter.joinpath(".github", "workflows", "briefing.yml").read_text()
        hour, minute = map(int, state["start"].split(":"))
        hours = ",".join(str(value) for value in range(hour, min(hour + 3, 24)))
        schedule = f"{minute} {hours} * * *"
        text = text.replace('cron: "0 7,8,9 * * *"', "cron: " + json.dumps(schedule))
        # actionlint requires the IANA name rather than the UTC alias in schedules.
        timezone = "Etc/UTC" if state["timezone"] == "UTC" else state["timezone"]
        text = text.replace('timezone: "Etc/UTC"', "timezone: " + json.dumps(timezone))
        text = text.replace(
            'smtp-host: "smtp.gmail.com"', "smtp-host: " + json.dumps(state["host"])
        )
        text = text.replace('smtp-port: "465"', "smtp-port: " + json.dumps(str(state["port"])))
        text = text.replace('mail-to: ""', "mail-to: " + json.dumps(state["recipient"]))
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(text, encoding="utf-8")
    state["prepared"] = True
    _save(root, state)


def _repo(gh: Path, name: str) -> dict | None:
    """Read exact repository identity; distinguish absence from API/network failure."""
    result = run_gh(gh, ["repo", "view", name, "--json", REPO_FIELDS], check=False)
    if result.returncode:
        # gh does not have a distinct exit status for a missing repository. Verify 404
        # with the API rather than treating arbitrary network/auth failures as absence.
        result = run_gh(gh, ["api", f"repos/{name}", "--include"], check=False)
        if result.returncode and re.search(r"^HTTP/\S+ 404(?: |$)", result.stdout, re.M):
            return None
        raise SetupError("Could not verify repository availability. Check GitHub access and retry.")
    return json.loads(result.stdout)


def _verify_repo(repo: dict, state: dict) -> None:
    """Require an exact private repository owned by the confirmed personal account."""
    if (
        repo.get("nameWithOwner") != state["repo"]
        or not repo.get("isPrivate")
        or repo.get("owner", {}).get("login") != state["owner"]
        or not repo.get("id")
        or (state.get("repo_id") and repo["id"] != state["repo_id"])
    ):
        raise SetupError("Repository identity or privacy changed; setup cannot continue.")


def _secret_names(gh: Path, name: str) -> set[str]:
    """Read secret names only; secret values are never retrieved."""
    result = run_gh(gh, ["secret", "list", "--repo", name, "--json", "name"])
    return {item["name"] for item in json.loads(result.stdout)}


def _launch(root: Path, state: dict, gh: Path) -> int:
    """Offer a single dispatch and report its actual run status without polling forever."""
    actions = f"https://github.com/{state['repo']}/actions"
    if state.get("launch_offered") or state.get("dispatch_intent"):
        print(f"Ready. Use Run workflow later: {actions}")
        return 0
    if not _confirm("Launch the first cloud briefing now?"):
        state["launch_offered"] = True
        _save(root, state)
        print(f"Ready. Use Run workflow later: {actions}")
        return 0
    previous = run_gh(
        gh,
        [
            "run",
            "list",
            "--repo",
            state["repo"],
            "--workflow",
            "briefing.yml",
            "--event",
            "workflow_dispatch",
            "--json",
            "databaseId,url,status,conclusion",
            "--limit",
            "10",
        ],
    )
    old_ids = {run["databaseId"] for run in json.loads(previous.stdout)}
    state["dispatch_intent"] = True
    _save(root, state)
    try:
        run_gh(gh, ["workflow", "run", "briefing.yml", "--repo", state["repo"], "--ref", "main"])
    except CommandError:
        print(f"Dispatch outcome is uncertain. Check Actions before using Run workflow: {actions}")
        print(
            f"Resume with daily-briefing init {shlex.quote(str(root))}; "
            "setup will not dispatch again."
        )
        return 1
    state["launch_offered"] = True
    _save(root, state)
    try:
        result = run_gh(
            gh,
            [
                "run",
                "list",
                "--repo",
                state["repo"],
                "--workflow",
                "briefing.yml",
                "--event",
                "workflow_dispatch",
                "--json",
                "databaseId,url,status,conclusion",
                "--limit",
                "10",
            ],
        )
        runs = [run for run in json.loads(result.stdout) if run["databaseId"] not in old_ids]
    except CommandError:
        runs = []
    if len(runs) == 1:
        run = runs[0]
        print(f"Cloud run {run['status']}: {run['url']}")
    else:
        print(f"Dispatch accepted; the run may take a moment to appear. Check Actions: {actions}")
    print("Follow the cloud login email if ChatGPT needs connecting.")
    return 0


def _check_initial_git(root: Path, state: dict) -> tuple[str, ...]:
    """Reject unrelated index entries and every unsafe initial outgoing tree, read-only."""
    selected = state["sections"]
    presets = {path.name for path in _starter().joinpath("sections").iterdir()}
    if not selected or any(name not in presets for name in selected):
        raise SetupError("Initial section selection does not match the starter presets.")
    allowed = (*INITIAL_FILES, *(f"sections/{name}" for name in selected))
    branch = git(root, "symbolic-ref", "--short", "HEAD", check=False)
    if branch.returncode or branch.stdout.strip() != "main":
        raise SetupError("Return to the setup's main branch before initial publication.")
    for entry in git(root, "ls-files", "--stage", "-z").stdout.split("\0"):
        if entry:
            metadata, path = entry.split("\t", 1)
            mode, _, stage = metadata.split()
            if path not in allowed or mode not in ("100644", "100755") or stage != "0":
                raise SetupError("Unsafe or unrelated staged files; index and files are preserved.")
    if not git(root, "rev-parse", "--verify", "HEAD", check=False).returncode:
        commits = git(root, "--no-replace-objects", "rev-list", "HEAD").stdout.splitlines()
        for commit in commits:
            tree = git(root, "--no-replace-objects", "ls-tree", "-r", "-z", commit).stdout
            for entry in tree.split("\0"):
                if entry:
                    metadata, path = entry.split("\t", 1)
                    mode, kind, _ = metadata.split()
                    if path not in allowed or mode not in ("100644", "100755") or kind != "blob":
                        raise SetupError(
                            "Unsafe initial Git history, including earlier deleted "
                            "files; index and files are preserved."
                        )
    for path in allowed:
        if not (root / path).is_file() or (root / path).is_symlink():
            raise SetupError("Initial starter files must be regular files.")
    return allowed


def _initialize(root: Path, state: dict, gh: Path, account: dict) -> int:
    """Continue this setup's explicit preparation, creation and publication stages."""
    repo = _repo(gh, state["repo"]) if state.get("create_intent") else None
    if repo is not None:
        _verify_repo(repo, state)
        if not state.get("repo_id"):
            if not repo.get("isEmpty"):
                raise SetupError("Unconfirmed repository is not empty; cannot adopt it.")
            if not _confirm(
                f"Creation was uncertain. Confirm you created and own {state['repo']}?"
            ):
                return 1
            state["repo_id"] = repo["id"]
            _save(root, state)
    elif state.get("repo_id") or state.get("create_intent"):
        raise SetupError(
            "Repository creation is uncertain. Inspect GitHub before continuing; "
            "setup will not create another repository automatically."
        )
    if (
        repo
        and not repo.get("isEmpty")
        and not (state.get("push_intent") or state.get("published"))
    ):
        raise SetupError("Repository is no longer empty; stopping before secret upload.")
    existing = _secret_names(gh, state["repo"]) if repo else set()
    if state.get("push_intent") and not state.get("published"):
        remote = git(
            root,
            "ls-remote",
            f"https://github.com/{state['repo']}.git",
            "refs/heads/main",
            gh_bin=gh,
        ).stdout.split()
        if remote and remote[0] == state["initial_sha"]:
            state["published"] = True
            _save(root, state)
        else:
            raise SetupError(
                "Push outcome is uncertain. Inspect origin/main before retrying; "
                "setup will not push again automatically."
            )
    if state.get("published"):
        if SECRET_NAMES - existing:
            raise SetupError(
                "Published repository is missing secret names. Restore them in "
                "GitHub Settings; setup never resets published credentials."
            )
        return _launch(root, state, gh)
    settings = _credentials(state) if {"SMTP_USER", "SMTP_PASSWORD"} - existing else None
    _save(root, state)
    if not state.get("prepared"):
        _collect(root, state)
    allowed = _check_initial_git(root, state)
    print(f"Publish {root} to private repository {state['repo']}?")
    print(f"Recipient: {state['recipient']}")
    print("Sections:")
    for name in state["sections"]:
        section = parse_section((root / "sections" / name).read_text(), Path(name).stem)
        print(f"  {section.title} ({name})")
    print(f"Schedule: {state['start']} {state['timezone']}, up to two same-day hourly retries.")
    print("SMTP secrets are uploaded before the workflow is pushed.")
    if not _confirm("Publish these accepted files"):
        print(f"Files saved. Resume with daily-briefing init {shlex.quote(str(root))}")
        return 0
    if repo is None:
        if _repo(gh, state["repo"]) is not None:
            raise SetupError(
                "Repository already exists and is not owned by this setup. "
                "Choose another repository name in a new directory."
            )
        state["create_intent"] = True
        _save(root, state)
        run_gh(gh, ["repo", "create", state["repo"], "--private"])
        repo = _repo(gh, state["repo"])
        if repo is None:
            raise SetupError("Creation outcome is uncertain. Inspect GitHub before resuming.")
        _verify_repo(repo, state)
        if not repo.get("isEmpty"):
            raise SetupError("New repository is not empty; stopping before secret upload.")
        state["repo_id"] = repo["id"]
        _save(root, state)
    _verify_repo(repo, state)
    missing = SECRET_NAMES - existing
    if settings is not None:
        # Before publication, keep a partially uploaded pair consistent with the SMTP test.
        missing |= {"SMTP_USER", "SMTP_PASSWORD"}
    for name in sorted(missing):
        value = (
            secrets.token_urlsafe(48)
            if name == "BRIEFING_KEY"
            else settings.user
            if name == "SMTP_USER"
            else settings.password
        )
        state["secret_intent"] = name
        _save(root, state)
        run_gh(gh, ["secret", "set", name, "--repo", state["repo"]], input_text=value)
    state.pop("secret_intent", None)
    _save(root, state)
    if SECRET_NAMES - _secret_names(gh, state["repo"]):
        raise SetupError("Not all secret names are present; stopping before workflow publication.")
    remote = f"https://github.com/{state['repo']}.git"
    origin = git(root, "remote", "get-url", "origin", check=False)
    if origin.returncode:
        git(root, "remote", "add", "origin", remote)
    elif origin.stdout.strip() != remote:
        raise SetupError("Local origin does not match this setup repository.")
    # Exact files keep unrelated untracked data in sections/state out of the index.
    git(root, "add", "--", *allowed)
    _check_initial_git(root, state)
    if (
        git(root, "rev-parse", "--verify", "HEAD", check=False).returncode
        or git(root, "diff", "--cached", "--quiet", check=False).returncode
    ):
        git(
            root,
            "-c",
            f"user.name={account['login']}",
            "-c",
            f"user.email={account['id']}+{account['login']}@users.noreply.github.com",
            "commit",
            "-m",
            "Set up my daily briefing",
        )
    _check_initial_git(root, state)
    state["initial_sha"] = git(root, "rev-parse", "HEAD").stdout.strip()
    state["push_intent"] = True
    _save(root, state)
    git(root, "push", "--set-upstream", "origin", "main", gh_bin=gh)
    state["published"] = True
    _save(root, state)
    print(f"Published private briefing: https://github.com/{state['repo']}")
    return _launch(root, state, gh)


def initialize(directory: Path) -> int:
    """Guide personal setup, preserving accepted files and uncertain mutation intent.

    Args:
        directory: Default local repository directory; the user can choose another.

    Returns:
        Zero when ready or safely declined, one when recovery is required.

    Raises:
        SetupCancelled: Input was cancelled, with the accepted recovery directory.
    """
    root = directory.expanduser().absolute()
    try:
        if platform.system() not in ("Darwin", "Linux") or platform.machine().lower() not in (
            "x86_64",
            "amd64",
            "aarch64",
            "arm64",
        ):
            raise SetupError("Use macOS, Linux or WSL on x86-64 or ARM64.")
        for name in ("git", "uv"):
            if not shutil.which(name):
                raise SetupError(f"Install {name} first, then rerun daily-briefing init.")
        _safe_directory(root)
        gh = ensure_tool("gh")
        if run_gh(gh, ["auth", "status", "--hostname", "github.com"], check=False).returncode:
            run_gh(
                gh,
                [
                    "auth",
                    "login",
                    "--hostname",
                    "github.com",
                    "--git-protocol",
                    "https",
                    "--web",
                    "--scopes",
                    "workflow",
                ],
                capture=False,
            )
        account = json.loads(run_gh(gh, ["api", "user"]).stdout)
        if account.get("type") != "User" or not account.get("login") or not account.get("id"):
            raise SetupError("Use a personal GitHub account for this private briefing.")
        state_path = root / ".git" / STATE
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if (
                state.get("version") != 1
                or state.get("owner") != account["login"]
                or state.get("account_id") != account["id"]
            ):
                raise SetupError("This setup belongs to a different GitHub account or version.")
        else:
            print(f"GitHub personal account: {account['login']}")
            if not _confirm("Use this account"):
                return 0
            name = _ask(
                "Repository name",
                "my-briefing",
                lambda value: bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value)),
            )
            root = Path(_ask("Local directory", str(root))).expanduser().absolute()
            _safe_directory(root)
            if (root / ".git" / STATE).exists():
                raise SetupError("Run init with this existing setup directory to resume it.")
            root.mkdir(parents=True, exist_ok=True)
            git(root, "init", "-b", "main")
            state = {
                "version": 1,
                "owner": account["login"],
                "account_id": account["id"],
                "repo": f"{account['login']}/{name}",
            }
            _save(root, state)
        if "provider" not in state:
            provider = _ask(
                "Email provider (Gmail/iCloud/Fastmail/custom)",
                "gmail",
                lambda value: value.lower() in {*PROVIDERS, "custom"},
            ).lower()
            if provider == "custom":
                host = _ask(
                    "SMTP host",
                    valid=lambda value: bool(
                        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value)
                    ),
                )
                port = int(
                    _ask(
                        "SMTP port",
                        "465",
                        lambda value: value.isdigit() and 1 <= int(value) <= 65535,
                    )
                )
            else:
                host, port = PROVIDERS[provider]
            state.update(provider=provider, host=host, port=port)
            _save(root, state)
        return _initialize(root, state, gh, account)
    except (KeyboardInterrupt, EOFError):
        raise SetupCancelled(root) from None
    except (
        SetupError,
        SectionError,
        BootstrapError,
        CommandError,
        OSError,
        ValueError,
        KeyError,
    ) as error:
        print(f"Setup stopped: {error}")
        print(
            "Accepted files are preserved. Resume with "
            f"daily-briefing init {shlex.quote(str(root))}"
        )
        return 1
