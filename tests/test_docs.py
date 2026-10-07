from pathlib import Path

from daily_briefing import cli

ROOT = Path(__file__).resolve().parents[1]


def test_sample_renders(tmp_path):
    out = tmp_path / "p.html"
    args = [
        "preview",
        str(ROOT / "examples/sample-briefing.md"),
        "--sections",
        str(ROOT / "template/sections"),
        "-o",
        str(out),
    ]
    assert cli.main(args) == 0
    html = out.read_text(encoding="utf-8")
    assert html.count("<h2 ") == 5
    assert ">Research</h2>" in html and ">Book ahead</h2>" in html


def test_readme_covers_essentials():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in (
        "docs/screenshot.png",
        "Use this template",
        "private",
        "BRIEFING_KEY",
        "Run workflow",
        "smtp-port",
        "uv run pytest",
    ):
        assert needle in text, needle


def test_changelog_has_first_release():
    assert "## 1.0.0" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
