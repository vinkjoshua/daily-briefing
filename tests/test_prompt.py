from datetime import date

from daily_briefing.prompt import build_prompt
from daily_briefing.sections import Section

SECTIONS = [
    Section("10-a", "Research", "🧠", "Max 3 papers."),
    Section("20-b", "Open-source radar", "🛠️", "Max 3 repos costing $0."),
]


def test_prompt_contains_date_sections_and_skeleton():
    prompt = build_prompt(date(2026, 10, 7), SECTIONS)
    assert "Today is 2026-10-07." in prompt
    assert prompt.index("### 1. Research") < prompt.index("Max 3 papers.")
    assert prompt.index("Max 3 papers.") < prompt.index("### 2. Open-source radar")
    output = prompt.split("## Output", 1)[1]
    assert output.index("## Research") < output.index("## Open-source radar")
    assert "$0" in prompt
    assert "$sections" not in prompt and "$skeleton" not in prompt


def test_prompt_keeps_safety_rules():
    prompt = build_prompt(date(2026, 10, 7), SECTIONS[:1])
    assert "no network access" in prompt
    assert "state/seen.md" in prompt
    assert "Only change files under `state/`" in prompt
    assert '"Sources:"' in prompt
