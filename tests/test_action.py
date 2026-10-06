import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
STEPS = ACTION["runs"]["steps"]


def step(step_id):
    return next(s for s in STEPS if s.get("id") == step_id)


def test_composite_and_inputs_declared():
    assert ACTION["runs"]["using"] == "composite"
    used = set(re.findall(r"inputs\.([a-z-]+)", (ROOT / "action.yml").read_text()))
    assert used <= set(ACTION["inputs"])
    for name in ("smtp-user", "smtp-password", "auth-key"):
        assert ACTION["inputs"][name]["required"] is True


def test_guard_runs_before_setup():
    ids = [s.get("id") or s.get("uses", "") for s in STEPS]
    guard = ids.index("guard")
    node = next(i for i, x in enumerate(ids) if "setup-node" in x)
    assert guard < node


def test_persist_always_runs():
    assert "always()" in step("persist")["if"]


def test_action_secret_scoping():
    guard_env = step("guard").get("env", {})
    persist_env = step("persist")["env"]
    run_env = step("run")["env"]
    assert "SMTP_PASSWORD" not in guard_env and "BRIEFING_KEY" not in guard_env
    assert set(guard_env) <= {"BRIEFING_TIMEZONE", "BRIEFING_FORCE", "HAS_AUTH_KEY"}
    assert guard_env["HAS_AUTH_KEY"] == "${{ inputs.auth-key != '' }}"
    assert "SMTP_PASSWORD" not in persist_env
    assert "GITHUB_TOKEN" not in run_env
    assert persist_env["GITHUB_TOKEN"] == "${{ inputs.github-token }}"


def test_actions_pinned_to_existing_refs():
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert "astral-sh/setup-uv@v10.2.0" in text
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "astral-sh/setup-uv@v10.2.0" in ci


def test_uv_runs_skip_dev_dependencies():
    uv_steps = [s for s in STEPS if "uv run" in s.get("run", "")]
    assert len(uv_steps) == 3
    assert all("--no-dev" in s["run"] for s in uv_steps)


def test_setup_uv_does_not_cache():
    setup = next(s for s in STEPS if "setup-uv" in s.get("uses", ""))
    assert setup["with"]["enable-cache"] is False
