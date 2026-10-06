from datetime import UTC, date, datetime

import pytest

from daily_briefing.state import Paths, already_sent, mark_notified, today_in, was_notified


def test_today_uses_timezone():
    late_utc = datetime(2026, 10, 6, 22, 30, tzinfo=UTC)
    assert today_in("Europe/Amsterdam", late_utc) == date(2026, 10, 7)
    assert today_in("UTC", late_utc) == date(2026, 10, 6)


def test_paths(tmp_path):
    p = Paths(tmp_path)
    day = date(2026, 10, 7)
    assert p.briefing(day) == tmp_path / "briefings" / "2026-10-07.md"
    assert p.draft(day) == tmp_path / "briefings" / "2026-10-07.md.tmp"
    assert p.auth_blob == tmp_path / ".briefing" / "codex-auth.enc"
    assert p.sections_dir == tmp_path / "sections"


def test_already_sent_needs_non_empty_file(tmp_path):
    p, day = Paths(tmp_path), date(2026, 10, 7)
    assert not already_sent(p, day)
    p.briefing(day).parent.mkdir()
    p.briefing(day).write_text("")
    assert not already_sent(p, day)
    p.briefing(day).write_text("# hi")
    assert already_sent(p, day)


def test_notified_is_per_day_and_kind(tmp_path):
    p = Paths(tmp_path)
    d1, d2 = date(2026, 10, 7), date(2026, 10, 8)
    assert not was_notified(p, d1, "reconnect")
    mark_notified(p, d1, "reconnect")
    assert was_notified(p, d1, "reconnect")
    assert not was_notified(p, d1, "failure")
    assert not was_notified(p, d2, "reconnect")
    mark_notified(p, d2, "failure")
    assert not was_notified(p, d1, "reconnect")


@pytest.mark.parametrize(
    "content",
    [
        b"[]",  # Valid JSON but not a dict
        b'{"date": "2026-10-07", "kinds": "reconnect"}',  # kinds is string, not list
        b"\xff\xfe",  # Invalid UTF-8
        b"not json",  # Invalid JSON
    ],
)
def test_corrupt_notified_file_is_ignored(tmp_path, content):
    p = Paths(tmp_path)
    day = date(2026, 10, 7)
    p.notified_file.parent.mkdir(parents=True, exist_ok=True)
    p.notified_file.write_bytes(content)
    assert not was_notified(p, day, "reconnect")
    mark_notified(p, day, "reconnect")
    assert was_notified(p, day, "reconnect")
