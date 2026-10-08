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


def test_sample_section_intros_and_links_survive_rendering():
    import re

    from daily_briefing.render import parse_briefing

    markdown = (ROOT / "examples/sample-briefing.md").read_text(encoding="utf-8")
    briefing = parse_briefing(markdown)
    assert [section.title for section in briefing.sections] == [
        "Research",
        "Open-source radar",
        "AI events & talks",
        "This week",
        "Book ahead",
    ]
    for section in briefing.sections:
        first_paragraph = re.match(r"<p[^>]*>(.*?)</p>", section.html, re.S)
        assert first_paragraph, section.title
        assert "<strong" not in first_paragraph.group(1), section.title
    markdown_links = re.findall(r"\]\((https://example\.org/[^)]+)\)", markdown)
    assert len(markdown_links) == 13
    for link in markdown_links:
        assert any(f'href="{link}"' in section.html for section in briefing.sections)
