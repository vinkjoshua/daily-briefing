import os
from pathlib import Path

import pytest

FAKE_CODEX = Path(__file__).parent / "fakes" / "fake_codex.py"


@pytest.fixture
def fake_codex() -> Path:
    os.chmod(FAKE_CODEX, 0o755)
    return FAKE_CODEX
