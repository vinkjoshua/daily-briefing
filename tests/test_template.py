from datetime import date
from pathlib import Path

import pytest
import yaml

from daily_briefing import cli
from daily_briefing.prompt import build_prompt
from daily_briefing.sections import load_sections

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"
PRIVATE_WORDS = ROOT / ".private-words"
SCANNED = (
    "src",
    "template",
    "examples",
    ".github",
    "README.md",
    "CHANGELOG.md",
    "action.yml",
    "LICENSE",
)


def test_template_validates():
    assert cli.main(["validate", "--dir", str(TEMPLATE)]) == 0


def test_template_sections():
    sections = load_sections(TEMPLATE / "sections")
    assert [s.title for s in sections] == [
        "Research",
        "Open-source radar",
        "AI events & talks",
        "This week",
        "Book ahead",
    ]
    assert all(s.icon != "•" for s in sections)
    assert "Book ahead" in build_prompt(date(2026, 10, 7), sections)


def test_workflow():
    wf = yaml.safe_load((TEMPLATE / ".github/workflows/briefing.yml").read_text())
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML parses `on` as True
    assert triggers["schedule"] == [{"cron": "41 4,5,6 * * *"}]
    assert "workflow_dispatch" in triggers
    assert wf["permissions"] == {"contents": "write"}
    assert wf["concurrency"]["cancel-in-progress"] is False
    steps = wf["jobs"]["briefing"]["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    assert steps[0]["with"]["ref"] == "${{ github.ref }}"
    assert wf["jobs"]["briefing"]["if"] == "${{ !github.event.repository.is_template }}"
    assert wf["jobs"]["briefing"]["timeout-minutes"] == 75
    assert steps[1]["uses"] == "vinkjoshua/daily-briefing@v1"
    assert steps[1]["with"]["auth-key"] == "${{ secrets.BRIEFING_KEY }}"


def test_readme_says_private():
    text = (TEMPLATE / "README.md").read_text(encoding="utf-8")
    assert "Private" in text and "BRIEFING_KEY" in text and "Run workflow" in text


def _private_words() -> list[str]:
    if not PRIVATE_WORDS.is_file():
        pytest.skip("no .private-words file")
    lines = PRIVATE_WORDS.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def test_no_personal_data_in_public_code():
    words = _private_words()
    for name in SCANNED:
        base = ROOT / name
        for path in [base] if base.is_file() else sorted(base.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for word in words:
                assert word not in text, f"{word!r} found in {path}"
