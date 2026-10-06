import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

FAKE_CODEX = Path(__file__).parent / "fakes" / "fake_codex.py"


@pytest.fixture
def fake_codex() -> Path:
    os.chmod(FAKE_CODEX, 0o755)
    return FAKE_CODEX


@pytest.fixture
def codex_tree(fake_codex, tmp_path):
    """Run the actual wrapper in a foreground owner with an isolated fake process tree."""
    parentfile, childfile = tmp_path / "codex.pid", tmp_path / "child.pid"
    extra = {
        "FAKE_CODEX_EXEC": "hang-child",
        "FAKE_CODEX_LOGIN": "hang-child",
        "FAKE_CODEX_PARENT_PIDFILE": str(parentfile),
        "FAKE_CODEX_PIDFILE": str(childfile),
    }

    def run(script, *, interrupt=False, exec_mode="hang-child"):
        extra["FAKE_CODEX_EXEC"] = exec_mode
        prelude = (
            "import sys\nfrom pathlib import Path\nfrom daily_briefing.codex import Codex\n"
            f"extra = {extra!r}\n"
            f"binary = {str(fake_codex)!r}\n"
            f"home = Path({str(tmp_path / 'auth')!r})\n"
            f"codex = Codex(binary, home, Path({str(tmp_path)!r}), extra_env=extra)\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", prelude + script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while (
                not (parentfile.exists() and parentfile.stat().st_size)
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert parentfile.exists(), proc.communicate(timeout=1)
            pids = [int(path.read_text()) for path in (parentfile, childfile)]
            if interrupt:
                proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=15)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                alive = []
                for pid in pids:
                    try:
                        os.kill(pid, 0)
                        alive.append(pid)
                    except ProcessLookupError:
                        pass
                if not alive:
                    break
                time.sleep(0.01)
            assert not alive, f"Owned Codex processes survived owner exit: {alive}"
            return subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
        finally:
            if parentfile.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(int(parentfile.read_text()), signal.SIGTERM)
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=5)

    return run
