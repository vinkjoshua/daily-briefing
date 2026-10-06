from daily_briefing.render import (
    PALETTE,
    markdown_to_html,
    parse_briefing,
    render_html,
    strip_preamble,
)

DOC = """Here is your briefing:

# Daily briefing — Tuesday 6 October
**Action today:** Buy **Museumnacht** tickets.

## LLM engineering
**Try:** something.

## Open-source radar
- **Claude** — A meetup.
- plain item

## Book ahead
**ACTION**

- [Museumnacht — 7 November](https://example.com): buy now.

**On the radar**

| What | When |
|---|---|
| Thing | Fri |
## Extra
Text

Sources: example.com failed.
"""

ICONS = {"LLM engineering": "🧠", "Open-source radar": "🛠️"}


def test_preamble_dropped():
    assert strip_preamble(DOC).startswith("# Daily briefing")


def test_header_fields():
    b = parse_briefing(DOC, ICONS)
    assert b.subject == "Daily briefing — Tuesday 6 October"
    assert (b.kicker, b.headline) == ("Daily briefing", "Tuesday 6 October")
    assert b.read_min >= 1
    assert "Museumnacht" in b.action_html and not b.action_html.startswith("<p")
    assert b.preheader == "Buy Museumnacht tickets."


def test_sections_and_icons():
    b = parse_briefing(DOC, ICONS)
    assert [s.title for s in b.sections] == [
        "LLM engineering",
        "Open-source radar",
        "Book ahead",
        "Extra",
    ]
    assert [s.icon for s in b.sections] == ["🧠", "🛠️", "•", "•"]


def test_icon_lookup_ignores_case_and_numbering():
    b = parse_briefing("# T\n\n## 2. open-source RADAR\nx\n", ICONS)
    assert b.sections[0].icon == "🛠️"


def test_heading_after_table_still_splits():
    b = parse_briefing(DOC, ICONS)
    book = b.sections[2].html
    assert "<table" in book and "Extra" not in book


def test_sources_line_moves_to_note():
    b = parse_briefing(DOC, ICONS)
    assert b.note == "Sources: example.com failed."
    assert "Sources:" not in b.sections[-1].html


def test_no_sections_goes_to_intro():
    b = parse_briefing("Some text without structure.\n\n- a list\n")
    assert b.sections == []
    assert "Some text" in b.intro_html and "<li" in b.intro_html
    assert b.subject == "Daily briefing"


def test_pills_badges_and_labels():
    html = parse_briefing(DOC, ICONS).sections[2].html + parse_briefing(DOC).sections[1].html
    assert f'background:{PALETTE["deep"]}; color:#ffffff;">ACTION</span>' in html
    assert f'background:{PALETTE["mint"]}; color:{PALETTE["deep"]};">On the radar</span>' in html
    assert ">Claude</span> A meetup." in html
    assert "<li" in html


def test_lead_in_labels_turn_green():
    html = markdown_to_html("**Try:** this")
    assert f'color:{PALETTE["green"]};">Try:</strong>' in html


def test_list_directly_after_paragraph():
    assert "<li" in markdown_to_html("Intro line\n- item\n")


def test_every_paragraph_inline_styled():
    html = markdown_to_html("one\n\ntwo\n")
    assert html.count('<p style="') == 2


def test_render_html():
    html = render_html(
        parse_briefing(DOC, ICONS),
        repo_url="https://github.com/a/b",
        generated="now",
    )
    for text in ("Tuesday 6 October", "LLM engineering", "Book ahead", "4 sections", "now"):
        assert text in html
    assert "https://github.com/a/b" in html
    assert PALETTE["deep"] in html
    assert "{{" not in html


def test_singular_section_count():
    html = render_html(parse_briefing("# T\n\n## Only\nx\n"))
    assert "1 section<" in html


def test_raw_html_is_escaped():
    from daily_briefing.render import markdown_to_html

    html = markdown_to_html("hi <img src=x onerror=alert(1)> <script>alert(1)</script>")
    assert "<img" not in html and "<script" not in html
    assert "&lt;script&gt;" in html


def test_markdown_images_are_not_rendered():
    from daily_briefing.render import markdown_to_html

    assert "<img" not in markdown_to_html("![a](https://track.example/p.png)")
