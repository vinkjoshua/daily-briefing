import json
import os
import time

import pytest

from daily_briefing.codex import ENV_ALLOWLIST, Codex, CodexResult

SECRETS = {
    "SMTP_PASSWORD": "pw",
    "BRIEFING_KEY": "k" * 32,
    "GITHUB_TOKEN": "ghs_x",
    "ACTIONS_RUNTIME_TOKEN": "rt",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "id",
}


def make(fake_codex, tmp_path, **extra):
    log = tmp_path / "calls.jsonl"
    base = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), **SECRETS}
    codex = Codex(
        str(fake_codex),
        tmp_path / "codex-home",
        tmp_path,
        base_env=base,
        extra_env={"FAKE_CODEX_LOG": str(log), **extra},
    )
    return codex, log


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_child_env_drops_secrets(fake_codex, tmp_path):
    codex, _ = make(fake_codex, tmp_path)
    env = codex.child_env()
    assert not set(SECRETS) & set(env)
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["CODEX_HOME"] == str(tmp_path / "codex-home")
    assert set(env) <= set(ENV_ALLOWLIST) | {"CODEX_HOME", "FAKE_CODEX_LOG"}


def test_exec_does_not_leak_env(fake_codex, tmp_path):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    codex.exec("hello")
    assert not set(SECRETS) & set(calls(log)[0]["env"])


def test_exec_passes_prompt_flags_and_writes_output(fake_codex, tmp_path):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    out = tmp_path / "out.md"
    result = codex.exec("the prompt", out_path=out, effort="high", model="gpt-x")
    assert result.ok and "OK" in result.output
    assert out.read_text().startswith("# Daily briefing")
    call = calls(log)[0]
    assert call["prompt"] == "the prompt"
    args = call["args"]
    assert args[:2] == ["exec", "-"]
    for flag in ("--skip-git-repo-check", "--ephemeral", 'web_search="live"', "workspace-write"):
        assert flag in args
    assert 'model_reasoning_effort="high"' in args
    assert args[args.index("-m") + 1] == "gpt-x"
    assert args[args.index("-C") + 1] == str(tmp_path)


def test_exec_failure_and_auth_output(fake_codex, tmp_path):
    codex, _ = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="auth-file")
    result = codex.exec("x")
    assert not result.ok and "401 Unauthorized" in result.output


def test_exec_timeout(fake_codex, tmp_path):
    codex, _ = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="hang")
    result = codex.exec("x", timeout=0.5)
    assert result.returncode == 124 and "timed out" in result.output


def test_exec_timeout_kills_grandchildren(fake_codex, tmp_path):
    pidfile = tmp_path / "child.pid"
    codex, _ = make(
        fake_codex, tmp_path, FAKE_CODEX_EXEC="hang-child", FAKE_CODEX_PIDFILE=str(pidfile)
    )
    result = codex.exec("x", timeout=1.5)
    assert result.returncode == 124 and "timed out" in result.output
    pid = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_probe_is_cheap_and_read_only(fake_codex, tmp_path):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    assert codex.probe().ok
    args = calls(log)[0]["args"]
    assert "read-only" in args and 'model_reasoning_effort="low"' in args
    assert 'web_search="live"' not in args


def test_device_login_success(fake_codex, tmp_path):
    codex, _ = make(fake_codex, tmp_path)
    prompts = []
    result = codex.device_login(lambda url, code: prompts.append((url, code)))
    assert result.ok and "Successfully logged in" in result.output
    assert prompts == [("https://auth.openai.com/codex/device", "ABCD-12345")]
    assert (tmp_path / "codex-home" / "auth.json").is_file()


def test_device_login_expired(fake_codex, tmp_path):
    codex, _ = make(fake_codex, tmp_path, FAKE_CODEX_LOGIN="expire")
    prompts = []
    result = codex.device_login(lambda url, code: prompts.append(code))
    assert not result.ok and "expired" in result.output
    assert prompts == ["ABCD-12345"]


@pytest.mark.parametrize(
    "web_search,want", [(True, 'web_search="live"'), (False, 'web_search="disabled"')]
)
def test_exec_isolates_config_rules_and_docs(fake_codex, tmp_path, web_search, want):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    codex.exec("x", web_search=web_search)
    args = calls(log)[0]["args"]
    assert want in args
    assert "project_doc_max_bytes=0" in args
    assert "--ignore-user-config" in args and "--ignore-rules" in args


@pytest.mark.parametrize("store", ["file", "keyring", "auto"])
def test_exec_preserves_only_auth_store_from_config(fake_codex, tmp_path, store):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    codex.codex_home.mkdir()
    config = codex.codex_home / "config.toml"
    config.write_text(f'cli_auth_credentials_store = "{store}"\nmodel = "ignored-model"\n')
    before = config.read_bytes()
    codex.exec("x")
    args = calls(log)[0]["args"]
    assert f'cli_auth_credentials_store="{store}"' in args
    assert "ignored-model" not in args
    assert config.read_bytes() == before


def test_exec_toml_encodes_reasoning_effort(fake_codex, tmp_path):
    import tomllib

    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    effort = 'high"\nweb_search="live'
    codex.exec("x", effort=effort, web_search=False)
    args = calls(log)[0]["args"]
    encoded = next(arg for arg in args if arg.startswith("model_reasoning_effort="))
    assert tomllib.loads(encoded) == {"model_reasoning_effort": effort}


@pytest.mark.parametrize(
    "mode,code,fragment", [("hang", 124, "timed out"), ("error", 3, "503"), ("silent", 1, "")]
)
def test_device_login_retains_error_and_timeout(fake_codex, tmp_path, mode, code, fragment):
    codex, _ = make(fake_codex, tmp_path, FAKE_CODEX_LOGIN=mode)
    prompts = []
    result = codex.device_login(lambda *args: prompts.append(args), timeout=0.5)
    assert isinstance(result, CodexResult)
    assert result.returncode == code and fragment in result.output
    assert prompts == []


@pytest.mark.parametrize(
    "config",
    ['cli_auth_credentials_store = ["file"]', 'cli_auth_credentials_store = "bad"', "invalid TOML"],
)
def test_exec_rejects_invalid_auth_store_without_printing_config(fake_codex, tmp_path, config):
    codex, log = make(fake_codex, tmp_path, FAKE_CODEX_EXEC="ok")
    codex.codex_home.mkdir()
    (codex.codex_home / "config.toml").write_text(config + '\nsecret = "test-only-secret"\n')
    with pytest.raises(ValueError, match="credential-store") as error:
        codex.exec("x")
    assert "test-only-secret" not in str(error.value)
    assert not log.exists()
