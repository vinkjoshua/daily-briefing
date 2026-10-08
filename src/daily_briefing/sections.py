"""Load email section definitions from sections/*.md files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_ICON = "•"


class SectionError(Exception):
    """Raised when a section file is missing or malformed."""


@dataclass(frozen=True)
class Section:
    """One email section, defined by a Markdown file with front matter.

    Attributes:
        slug: File name without extension, e.g. "20-open-source".
        title: Heading used in the email.
        icon: Optional emoji metadata, retained for compatibility.
        instructions: What Codex should put in this section.
    """

    slug: str
    title: str
    icon: str
    instructions: str


def parse_section(text: str, slug: str) -> Section:
    """Parse a section file.

    Args:
        text: File contents: a front matter block between --- lines, then instructions.
        slug: File name without extension, used in error messages.

    Returns:
        The parsed section.

    Raises:
        SectionError: If the file is malformed.
    """
    text = text.replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    if not text.startswith("---\n"):
        raise SectionError(f"{slug}: missing front matter (start the file with ---)")
    header, sep, body = text[4:].partition("---\n")
    if not sep or (header and not header.endswith("\n")):
        raise SectionError(f"{slug}: front matter is not closed with ---")
    meta: dict[str, str] = {}
    for line in header.splitlines():
        if not line.strip():
            continue
        key, colon, value = line.partition(":")
        if not colon:
            raise SectionError(f"{slug}: bad front matter line {line!r}")
        meta[key.strip().lower()] = value.strip()
    title = meta.get("title", "")
    if not title:
        raise SectionError(f"{slug}: front matter needs a title")
    if not body.strip():
        raise SectionError(f"{slug}: no instructions after the front matter")
    return Section(
        slug=slug, title=title, icon=meta.get("icon") or DEFAULT_ICON, instructions=body.strip()
    )


def load_sections(directory: Path) -> list[Section]:
    """Load every *.md section file in a directory, ordered by file name.

    Args:
        directory: Usually <repo>/sections.

    Returns:
        Sections in file-name order.

    Raises:
        SectionError: If there are no files, a file is malformed, or titles repeat.
    """
    files = sorted(directory.glob("*.md"))
    if not files:
        raise SectionError(f"No section files found in {directory}")
    sections = [parse_section(f.read_text(encoding="utf-8"), f.stem) for f in files]
    seen: set[str] = set()
    for section in sections:
        key = section.title.lower()
        if key in seen:
            raise SectionError(f"Duplicate section title {section.title!r}")
        seen.add(key)
    return sections
