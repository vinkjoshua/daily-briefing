"""Runtime configuration, read from the environment variables that action.yml sets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_KEY_LENGTH = 32
_TRUE = frozenset({"1", "true", "yes", "on"})
_REQUIRED = ("SMTP_USER", "SMTP_PASSWORD", "BRIEFING_KEY")


class ConfigError(Exception):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Settings for one briefing run.

    Attributes:
        workspace: Checked-out instance repository.
        timezone: IANA timezone that defines "today".
        smtp_host: SMTP server host.
        smtp_port: SMTP port; 465 means implicit TLS, anything else STARTTLS.
        smtp_user: SMTP login and sender address.
        smtp_password: SMTP password (for Gmail an App Password).
        mail_to: Recipient; defaults to smtp_user.
        auth_key: Passphrase that encrypts the saved Codex login.
        codex_bin: Codex executable.
        codex_home: CODEX_HOME directory used for this run.
        model: Optional Codex model override.
        effort: Codex reasoning effort.
        force: Send even if today's briefing already exists.
        event_name: GitHub event that started the run.
        repo_public: True only when the event explicitly reports a public repo.
        repo_url: Web URL of the repository, or "".
        workflow_url: Web URL of the workflow page with the Run workflow button, or "".
        run_url: Web URL of this run, or "".
    """

    workspace: Path
    timezone: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_to: str
    auth_key: str
    codex_bin: str
    codex_home: Path
    model: str
    effort: str
    force: bool
    event_name: str
    repo_public: bool
    repo_url: str
    workflow_url: str
    run_url: str

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, require_secrets: bool = True) -> Config:
        """Build a Config from environment variables.

        Args:
            env: Environment mapping, usually os.environ.
            require_secrets: Whether SMTP_USER, SMTP_PASSWORD and BRIEFING_KEY must be set.

        Returns:
            The parsed configuration.

        Raises:
            ConfigError: If a setting is missing or invalid.
        """

        def get(name: str, default: str = "") -> str:
            return (env.get(name) or "").strip() or default

        if require_secrets:
            missing = [name for name in _REQUIRED if not get(name)]
            if missing:
                raise ConfigError("Missing required settings: " + ", ".join(missing))
            if len(get("BRIEFING_KEY")) < MIN_KEY_LENGTH:
                raise ConfigError(
                    f"BRIEFING_KEY must be at least {MIN_KEY_LENGTH} characters; "
                    "generate one with a password manager."
                )

        port_raw = get("SMTP_PORT", "465")
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise ConfigError(f"SMTP_PORT must be a number, got {port_raw!r}.") from exc

        timezone = get("BRIEFING_TIMEZONE", "Europe/Amsterdam")
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(
                f"Unknown timezone {timezone!r}; use an IANA name like Europe/Amsterdam."
            ) from exc

        repo = get("GITHUB_REPOSITORY")
        server = get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
        repo_url = f"{server}/{repo}" if repo else ""
        run_id = get("GITHUB_RUN_ID")
        user = get("SMTP_USER")
        workspace = get("GITHUB_WORKSPACE")
        return cls(
            workspace=Path(workspace) if workspace else Path.cwd(),
            timezone=timezone,
            smtp_host=get("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=port,
            smtp_user=user,
            smtp_password=get("SMTP_PASSWORD"),
            mail_to=get("MAIL_TO", user),
            auth_key=get("BRIEFING_KEY"),
            codex_bin=get("CODEX_BIN", "codex"),
            codex_home=Path(get("CODEX_HOME", f"{get('RUNNER_TEMP', '/tmp')}/codex")),
            model=get("CODEX_MODEL"),
            effort=get("CODEX_EFFORT", "high"),
            force=get("BRIEFING_FORCE").lower() in _TRUE,
            event_name=get("GITHUB_EVENT_NAME"),
            repo_public=get("REPO_PRIVATE").lower() == "false",
            repo_url=repo_url,
            workflow_url=_workflow_url(repo_url, get("GITHUB_WORKFLOW_REF")),
            run_url=f"{repo_url}/actions/runs/{run_id}" if repo_url and run_id else "",
        )


def _workflow_url(repo_url: str, workflow_ref: str) -> str:
    """Return the workflow page URL for a GITHUB_WORKFLOW_REF value.

    Args:
        repo_url: Repository web URL, or "".
        workflow_ref: For example "ann/repo/.github/workflows/briefing.yml@refs/heads/main".

    Returns:
        The workflow page URL, the Actions tab if the ref is unknown, or "" outside Actions.
    """
    if not repo_url:
        return ""
    if "/.github/workflows/" not in workflow_ref:
        return f"{repo_url}/actions"
    filename = workflow_ref.split("/.github/workflows/", 1)[1].split("@", 1)[0]
    return f"{repo_url}/actions/workflows/{filename}"
