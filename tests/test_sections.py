import pytest

from daily_briefing.sections import Section, SectionError, load_sections, parse_section

GOOD = "---\ntitle: Open-source radar\nicon: 🛠️\n---\nMax 3 repos.\n"


def test_parse_section():
    assert parse_section(GOOD, "20-open-source") == Section(
        slug="20-open-source", title="Open-source radar", icon="🛠️", instructions="Max 3 repos."
    )


def test_icon_defaults_to_bullet():
    assert parse_section("---\ntitle: X\n---\nDo it.\n", "x").icon == "•"


def test_windows_line_endings():
    assert parse_section(GOOD.replace("\n", "\r\n"), "s").title == "Open-source radar"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("title: X\nDo it.\n", "missing front matter"),
        ("---\ntitle: X\nDo it.\n", "not closed"),
        ("---\nicon: 🧠\n---\nDo it.\n", "needs a title"),
        ("---\ntitle: X\n---", "no instructions"),
        ("---\ntitle X\n---\nDo it.\n", "bad front matter line"),
    ],
)
def test_invalid_sections(text, message):
    with pytest.raises(SectionError, match=message):
        parse_section(text, "bad")


def test_load_sections_sorted_by_filename(tmp_path):
    (tmp_path / "20-b.md").write_text("---\ntitle: B\n---\nb\n", encoding="utf-8")
    (tmp_path / "10-a.md").write_text("---\ntitle: A\n---\na\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    assert [s.title for s in load_sections(tmp_path)] == ["A", "B"]


def test_load_sections_requires_files(tmp_path):
    with pytest.raises(SectionError, match="No section files"):
        load_sections(tmp_path)


def test_duplicate_titles_rejected(tmp_path):
    (tmp_path / "10-a.md").write_text("---\ntitle: A\n---\na\n", encoding="utf-8")
    (tmp_path / "20-a.md").write_text("---\ntitle: a\n---\nb\n", encoding="utf-8")
    with pytest.raises(SectionError, match="Duplicate section title"):
        load_sections(tmp_path)
