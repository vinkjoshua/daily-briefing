"""Turn the briefing Markdown into the styled HTML email."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files

from jinja2 import Environment
from markdown_it import MarkdownIt

PALETTE: dict[str, str] = {
    "page": "#F7F4ED",
    "text": "#2D2728",
    "accent": "#713B46",
    "link": "#713B46",
    "muted": "#72676A",
    "border": "#DDCDC7",
}
C = PALETTE
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
SERIF = "Georgia, 'Times New Roman', serif"
MONO = "Consolas, Menlo, monospace"
DEFAULT_ICON = "•"
WRAP = "overflow-wrap:anywhere; word-break:break-word;"

# Email clients need explicit inline styles on content and layout cells.
TAG_STYLES: dict[str, str] = {
    "p": f"margin:0 0 16px; font-size:16px; line-height:1.65; color:{C['text']};",
    "ul": "margin:0 0 16px; padding-left:22px;",
    "ol": "margin:0 0 16px; padding-left:22px;",
    "li": f"margin:0 0 12px; font-size:16px; line-height:1.65; color:{C['text']};",
    "h3": f"margin:20px 0 8px; font-size:18px; color:{C['text']};",
    "a": f"color:{C['link']}; text-decoration:underline; {WRAP}",
    "strong": "color:inherit;",
    "code": f"color:{C['text']}; font-family:{MONO}; font-size:14px; {WRAP}",
    "pre": (
        f"margin:0 0 16px; padding:12px 0; border-top:1px solid {C['border']};"
        f" border-bottom:1px solid {C['border']}; font-family:{MONO};"
        f" font-size:14px; line-height:1.5; white-space:pre-wrap; {WRAP}"
    ),
    "table": (
        "border-collapse:collapse; table-layout:fixed; width:100%;"
        " margin:0 0 16px; font-size:14px; line-height:1.5;"
    ),
    "th": (
        f"color:{C['text']}; text-align:left; padding:8px 6px;"
        f" border-bottom:1px solid {C['border']}; {WRAP}"
    ),
    "td": f"padding:8px 6px; border-bottom:1px solid {C['border']}; vertical-align:top; {WRAP}",
    "blockquote": (
        f"margin:0 0 16px; padding:0 0 0 14px; border-left:1px solid {C['border']};"
        f" color:{C['text']};"
    ),
    "hr": f"border:0; border-top:1px solid {C['border']}; margin:24px 0;",
}

_MD = (
    MarkdownIt("commonmark", {"html": False})
    .enable("table")
    .enable("strikethrough")
    .disable("image")
)
_TEMPLATE = Environment(autoescape=True).from_string(
    files("daily_briefing").joinpath("template.html").read_text(encoding="utf-8")
)


@dataclass(frozen=True)
class RenderedSection:
    """One section in the email; icon metadata is retained for compatibility."""

    title: str
    icon: str
    html: str


@dataclass(frozen=True)
class Briefing:
    """A parsed briefing, ready for the HTML template."""

    subject: str
    kicker: str
    headline: str
    read_min: int
    action_html: str
    preheader: str
    intro_html: str
    sections: list[RenderedSection] = field(default_factory=list)
    note: str = ""
    markdown: str = ""


def strip_preamble(markdown: str) -> str:
    """Drop anything before the first H1 line, in case Codex adds chatter.

    Args:
        markdown: Raw Codex output.

    Returns:
        Markdown starting at the first "# " line (or unchanged if there is none).
    """
    lines = markdown.replace("\r\n", "\n").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("# ")), 0)
    return "\n".join(lines[start:]).strip() + "\n"


def _inline_styles(html: str) -> str:
    """Prepend TAG_STYLES to known tags, keeping any existing style last so it wins."""

    def repl(match: re.Match[str]) -> str:
        tag, attrs = match.group(1), match.group(2) or ""
        css = TAG_STYLES.get(tag)
        if not css:
            return match.group(0)
        close = " /" if attrs.rstrip().endswith("/") else ""
        attrs = attrs.rstrip().removesuffix("/").rstrip()
        if 'style="' in attrs:
            attrs = attrs.replace('style="', f'style="{css} ', 1)
        else:
            attrs += f' style="{css}"'
        return f"<{tag}{attrs}{close}>"

    return re.sub(r"<([a-z0-9]+)(\s[^>]*)?>", repl, html)


def markdown_to_html(markdown: str) -> str:
    """Render authored Markdown to restrained, inline-styled email HTML.

    Args:
        markdown: A Markdown fragment.

    Returns:
        HTML suitable for an email body.
    """
    return _inline_styles(_MD.render(markdown))


def _plain(markdown: str) -> str:
    """Rough Markdown-to-text for preview lines."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", markdown)
    return re.sub(r"[*_`#>]", "", text).strip()


def _normalise(title: str) -> str:
    return re.sub(r"^\d+[.)]\s*", "", title).strip().lower()


def _icon_for(title: str, icons: Mapping[str, str]) -> str:
    wanted = _normalise(title)
    for name, icon in icons.items():
        if _normalise(name) == wanted:
            return icon or DEFAULT_ICON
    return DEFAULT_ICON


def parse_briefing(markdown: str, icons: Mapping[str, str] | None = None) -> Briefing:
    """Split a briefing into header, action line, intro, sections and source note.

    Args:
        markdown: Codex output (preamble allowed).
        icons: Section title to emoji, usually from the section files.

    Returns:
        The parsed briefing.
    """
    icons = icons or {}
    md = strip_preamble(markdown)
    lines = md.splitlines()
    has_h1 = bool(lines) and lines[0].startswith("# ")
    title = lines[0][2:].strip() if has_h1 else "Daily briefing"
    body = lines[1:] if has_h1 else lines

    intro: list[str] = []
    raw: list[tuple[str, list[str]]] = []
    for line in body:
        if line.startswith("## "):
            raw.append((line[3:].strip(), []))
        elif raw:
            raw[-1][1].append(line)
        else:
            intro.append(line)

    action = ""
    rest: list[str] = []
    for line in intro:
        if line.startswith("**Action today:**"):
            action = line.removeprefix("**Action today:**").strip()
        else:
            rest.append(line)

    note = ""
    if raw:
        last = raw[-1][1]
        while last and not last[-1].strip():
            last.pop()
        if last and re.match(r"(?i)^\W*sources?\b", last[-1]):
            note = _plain(last.pop())

    kicker, _, headline = title.partition(" — ")
    words = len(re.findall(r"\w+", md))
    return Briefing(
        subject=title,
        kicker=kicker if headline else "Daily briefing",
        headline=headline or title,
        read_min=max(1, math.ceil(words / 230)),
        action_html=_inline_styles(_MD.renderInline(action)) if action else "",
        preheader=_plain(action) if action else "",
        intro_html=markdown_to_html("\n".join(rest)) if "".join(rest).strip() else "",
        sections=[
            RenderedSection(t, _icon_for(t, icons), markdown_to_html("\n".join(ls)))
            for t, ls in raw
        ],
        note=note,
        markdown=md,
    )


def render_html(briefing: Briefing, *, repo_url: str = "", generated: str = "") -> str:
    """Render a parsed briefing into the full HTML email.

    Args:
        briefing: Output of parse_briefing.
        repo_url: Link for "Edit your sections and interests"; omitted if empty.
        generated: Human-readable generation time for the footer.

    Returns:
        A complete HTML document.
    """
    return _TEMPLATE.render(
        subject=briefing.subject,
        preheader=briefing.preheader,
        kicker=briefing.kicker,
        headline=briefing.headline,
        read_min=briefing.read_min,
        action=briefing.action_html,
        intro=briefing.intro_html,
        sections=briefing.sections,
        note=briefing.note,
        generated=generated,
        repo_url=repo_url,
        c=PALETTE,
        font=FONT,
        serif=SERIF,
        wrap=WRAP,
    )
