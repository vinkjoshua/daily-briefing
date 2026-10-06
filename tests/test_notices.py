from daily_briefing.notices import (
    NOTICE_ICONS,
    device_code_notice,
    failure_notice,
    reconnect_notice,
)
from daily_briefing.render import parse_briefing

WORKFLOW = "https://github.com/ann/b/actions/workflows/briefing.yml"


def test_reconnect_notice():
    b = parse_briefing(reconnect_notice(WORKFLOW), NOTICE_ICONS)
    assert b.subject == "Daily briefing — reconnect needed"
    assert [s.title for s in b.sections] == ["Reconnect"]
    assert b.sections[0].icon == "🔑"
    assert WORKFLOW in b.sections[0].html
    assert "https://auth.openai.com/codex/device" in b.sections[0].html
    assert b.action_html


def test_device_code_notice():
    b = parse_briefing(
        device_code_notice("https://auth.openai.com/codex/device", "ABCD-12345"), NOTICE_ICONS
    )
    assert b.subject == "Daily briefing — your login code"
    assert "ABCD-12345" in b.action_html and "ABCD-12345" in b.sections[0].html


def test_failure_notice_keeps_last_40_lines_and_escapes_fences():
    reason = "\n".join(f"line {i}" for i in range(100)) + "\n```oops"
    md = failure_notice(reason, "https://github.com/ann/b/actions/runs/1")
    b = parse_briefing(md, NOTICE_ICONS)
    assert b.subject == "Daily briefing — run failed"
    assert "line 99" in md and "line 50" not in md
    assert "```oops" not in md
    assert "actions/runs/1" in b.sections[0].html
    assert b.sections[0].icon == "⚠️"


def test_failure_notice_without_run_url():
    assert "run log" not in failure_notice("boom", "")
