"""Verify the starter is available as an installed package resource."""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_built_wheel_exposes_complete_starter_resources(tmp_path, monkeypatch):
    build = pytest.importorskip("hatchling.build", reason="Hatchling unavailable in offline cache")
    monkeypatch.chdir(ROOT)
    wheel = tmp_path / build.build_wheel(str(tmp_path))
    with zipfile.ZipFile(wheel) as archive:
        for source in (ROOT / "template").rglob("*"):
            if source.is_file():
                relative = source.relative_to(ROOT / "template").as_posix()
                assert archive.read(f"daily_briefing/starter/{relative}") == source.read_bytes()
    # Use only the wheel on the package path, preventing source-tree fallback.
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import importlib.resources, json, sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "root = importlib.resources.files('daily_briefing').joinpath('starter'); "
            "print(json.dumps([root.joinpath('interests.md').is_file(), "
            "root.joinpath('.github/workflows/briefing.yml').is_file()]))",
            str(wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == [True, True]
