import pytest

from daily_briefing.config import Config, ConfigError

KEY = "k" * 32


def env(**overrides: str) -> dict[str, str]:
    base = {
        "SMTP_USER": "me@example.com",
        "SMTP_PASSWORD": "abcd efgh",
        "BRIEFING_KEY": KEY,
        "GITHUB_WORKSPACE": "/work",
        "RUNNER_TEMP": "/rt",
    }
    base.update(overrides)
    return base


def test_defaults():
    cfg = Config.from_env(env())
    assert cfg.timezone == "Europe/Amsterdam"
    assert (cfg.smtp_host, cfg.smtp_port) == ("smtp.gmail.com", 465)
    assert cfg.mail_to == "me@example.com"
    assert (cfg.effort, cfg.model, cfg.codex_bin) == ("high", "", "codex")
    assert str(cfg.codex_home) == "/rt/codex"
    assert str(cfg.workspace) == "/work"
    assert cfg.force is False


def test_missing_secrets_are_listed():
    with pytest.raises(ConfigError, match="SMTP_PASSWORD, BRIEFING_KEY"):
        Config.from_env(env(SMTP_PASSWORD="", BRIEFING_KEY=" "))


def test_secrets_optional_when_not_required():
    cfg = Config.from_env({"GITHUB_WORKSPACE": "/work"}, require_secrets=False)
    assert (cfg.smtp_user, cfg.auth_key, cfg.mail_to) == ("", "", "")


def test_short_key_rejected():
    with pytest.raises(ConfigError, match="at least 32"):
        Config.from_env(env(BRIEFING_KEY="short"))


def test_bad_port():
    with pytest.raises(ConfigError, match="SMTP_PORT"):
        Config.from_env(env(SMTP_PORT="abc"))


def test_bad_timezone():
    with pytest.raises(ConfigError, match="timezone"):
        Config.from_env(env(BRIEFING_TIMEZONE="Mars/Base"))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("false", False),
        ("", False),
    ],
)
def test_force_parsing(raw, expected):
    assert Config.from_env(env(BRIEFING_FORCE=raw)).force is expected


@pytest.mark.parametrize(("raw", "public"), [("false", True), ("true", False), ("", False)])
def test_public_only_when_event_says_so(raw, public):
    assert Config.from_env(env(REPO_PRIVATE=raw)).repo_public is public


def test_github_urls():
    cfg = Config.from_env(
        env(
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_REPOSITORY="ann/my-briefing",
            GITHUB_WORKFLOW_REF="ann/my-briefing/.github/workflows/briefing.yml@refs/heads/main",
            GITHUB_RUN_ID="42",
        )
    )
    assert cfg.repo_url == "https://github.com/ann/my-briefing"
    assert cfg.workflow_url == "https://github.com/ann/my-briefing/actions/workflows/briefing.yml"
    assert cfg.run_url == "https://github.com/ann/my-briefing/actions/runs/42"


def test_urls_empty_outside_actions():
    cfg = Config.from_env(env())
    assert (cfg.repo_url, cfg.workflow_url, cfg.run_url) == ("", "", "")


@pytest.mark.parametrize("password", [" leading middle trailing ", "   "])
def test_cloud_config_preserves_exact_custom_smtp_password(password):
    cfg = Config.from_env(env(SMTP_HOST="smtp.example.com", SMTP_PASSWORD=password))
    assert cfg.smtp_password == password
