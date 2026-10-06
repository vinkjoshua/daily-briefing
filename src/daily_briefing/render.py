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
    "deep": "#052e16",
    "green": "#166534",
    "accent": "#15803d",
    "link": "#065f46",
    "underline": "#86efac",
    "mint": "#dcfce7",
    "mint_light": "#f0fdf4",
    "mint_text": "#86efac",
    "page": "#e6eee9",
    "border": "#cfe0d5",
    "text": "#1f2937",
    "muted": "#5f6b66",
}
C = PALETTE
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MONO = "Consolas, Menlo, monospace"
DEFAULT_ICON = "•"

# Gmail is most reliable with inline styles, so every rendered tag gets one.
TAG_STYLES: dict[str, str] = {
    "p": f"margin:0 0 12px; font-size:14.5px; line-height:1.6; color:{C['text']};",
    "ul": "margin:0 0 12px; padding-left:20px;",
    "ol": "margin:0 0 12px; padding-left:20px;",
    "li": f"margin:0 0 10px; font-size:14.5px; line-height:1.6; color:{C['text']};",
    "h3": f"margin:16px 0 6px; font-size:15px; color:{C['deep']};",
    "a": f"color:{C['link']}; text-decoration:none; border-bottom:1px solid {C['underline']};",
    "strong": "color:#111827;",
    "code": (
        f"background:{C['mint_light']}; color:#065f46; border:1px solid {C['mint']};"
        f" border-radius:4px; padding:1px 5px; font-family:{MONO}; font-size:12.5px;"
    ),
    "pre": (
        f"background:{C['mint_light']}; border:1px solid {C['mint']}; border-radius:8px;"
        " padding:10px 12px; overflow-x:auto; font-size:12.5px; line-height:1.5;"
        " white-space:pre-wrap;"
    ),
    "table": "border-collapse:collapse; width:100%; margin:0 0 12px; font-size:13.5px;",
    "th": (
        f"background:{C['mint_light']}; color:{C['deep']}; text-align:left; padding:6px 8px;"
        f" border:1px solid {C['border']};"
    ),
    "td": f"padding:6px 8px; border:1px solid {C['border']}; vertical-align:top;",
    "blockquote": (
        f"margin:0 0 12px; padding:8px 14px; border-left:3px solid {C['accent']};"
        f" background:{C['mint_light']}; color:{C['deep']};"
    ),
    "hr": f"border:0; border-top:1px solid {C['border']}; margin:16px 0;",
}
PILL = (
    "display:inline-block; border-radius:999px; padding:3px 10px; font-size:11px;"
    " font-weight:700; letter-spacing:0.1em; text-transform:uppercase; margin:4px 0 10px;"
)
BADGE = (
    f"display:inline-block; background:{C['deep']}; color:#ffffff; border-radius:999px;"
    " padding:1px 8px; font-size:11px; font-weight:700; letter-spacing:0.04em; margin-right:4px;"
)

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
    """One section card in the email."""

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


def _pill(match: re.Match[str]) -> str:
    """Render a lone bold label paragraph as a pill; ALL-CAPS labels are dark."""
    label = match.group(1)
    colours = (
        f"background:{C['deep']}; color:#ffffff;"
        if label.isupper()
        else f"background:{C['mint']}; color:{C['deep']};"
    )
    return f'<div><span style="{PILL} {colours}">{label}</span></div>'


def markdown_to_html(markdown: str) -> str:
    """Render Markdown to inline-styled HTML with pills, badges and green lead-ins.

    Args:
        markdown: A Markdown fragment.

    Returns:
        HTML suitable for an email body.
    """
    html = _MD.render(markdown)
    html = re.sub(r"<p><strong>([^<:]{1,30})</strong></p>", _pill, html)
    html = re.sub(
        r"(<li>(?:\s*<p>)?)<strong>([^<]{1,20})</strong>\s*—\s*",
        lambda m: f'{m.group(1)}<span style="{BADGE}">{m.group(2)}</span> ',
        html,
    )
    html = re.sub(
        r"<strong>([^<]{1,25}:)</strong>",
        lambda m: f'<strong style="color:{C["green"]};">{m.group(1)}</strong>',
        html,
    )
    return _inline_styles(html)


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
    )
