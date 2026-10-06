"""Paths and once-per-day markers inside the instance repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def today_in(tz: str, now: datetime | None = None) -> date:
    """Return the current date in a timezone.

    Args:
        tz: IANA timezone name.
        now: Aware datetime to use instead of the clock.

    Returns:
        The local date.
    """
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


@dataclass(frozen=True)
class Paths:
    """Well-known locations in the instance repo."""

    root: Path

    def briefing(self, day: date) -> Path:
        """Archived briefing for a day (also the once-per-day guard)."""
        return self.root / "briefings" / f"{day.isoformat()}.md"

    def draft(self, day: date) -> Path:
        """Where Codex writes before the email is sent."""
        return self.root / "briefings" / f"{day.isoformat()}.md.tmp"

    @property
    def auth_blob(self) -> Path:
        """Encrypted Codex login."""
        return self.root / ".briefing" / "codex-auth.enc"

    @property
    def notified_file(self) -> Path:
        """Record of notices already sent today."""
        return self.root / ".briefing" / "notified.json"

    @property
    def sections_dir(self) -> Path:
        """Section definitions."""
        return self.root / "sections"


def already_sent(paths: Paths, day: date) -> bool:
    """Tell whether today's briefing was already sent.

    Args:
        paths: Repo paths.
        day: The briefing date.

    Returns:
        True if a non-empty archive file exists.
    """
    archive = paths.briefing(day)
    return archive.is_file() and archive.stat().st_size > 0


def _read(paths: Paths) -> dict[str, object]:
    """Read notified.json, treating any corruption as empty state."""
    try:
        data = json.loads(paths.notified_file.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("kinds"), list):
            return data
        return {}
    except (FileNotFoundError, OSError, ValueError):
        return {}


def was_notified(paths: Paths, day: date, kind: str) -> bool:
    """Tell whether a notice of this kind was already sent today.

    Args:
        paths: Repo paths.
        day: The briefing date.
        kind: "reconnect" or "failure".

    Returns:
        True if already sent.
    """
    data = _read(paths)
    return data.get("date") == day.isoformat() and kind in data.get("kinds", [])


def mark_notified(paths: Paths, day: date, kind: str) -> None:
    """Record that a notice was sent today.

    Args:
        paths: Repo paths.
        day: The briefing date.
        kind: "reconnect" or "failure".
    """
    data = _read(paths)
    if data.get("date") != day.isoformat():
        data = {"date": day.isoformat(), "kinds": []}
    kinds = list(data.get("kinds", []))
    if kind not in kinds:
        kinds.append(kind)
    paths.notified_file.parent.mkdir(parents=True, exist_ok=True)
    paths.notified_file.write_text(
        json.dumps({"date": day.isoformat(), "kinds": kinds}), encoding="utf-8"
    )
