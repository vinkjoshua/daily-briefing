from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_actionlint_installer_is_pinned():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "rhysd/actionlint/main/" not in ci
    assert "rhysd/actionlint/v" in ci
