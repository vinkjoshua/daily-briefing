"""Assemble the Codex prompt from the base prompt and the section files."""

from __future__ import annotations

from datetime import date
from importlib.resources import files
from string import Template

from daily_briefing.sections import Section


def build_prompt(today: date, sections: list[Section]) -> str:
    """Build the full prompt for one run.

    Args:
        today: The briefing date in the user's timezone.
        sections: Sections in email order.

    Returns:
        The prompt text sent to Codex on stdin.
    """
    base = Template(files("daily_briefing").joinpath("base_prompt.md").read_text(encoding="utf-8"))
    blocks = "\n\n".join(
        f"### {number}. {section.title}\n{section.instructions}"
        for number, section in enumerate(sections, start=1)
    )
    skeleton = "\n".join(f"## {section.title}" for section in sections)
    return base.substitute(today=today.isoformat(), sections=blocks, skeleton=skeleton)
