"""Fail CI if the installed release artifact or source distribution is incomplete."""

import shutil
import subprocess
import sys
import tarfile
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

import daily_briefing
from daily_briefing.setup import _starter

source = Path(sys.argv[1]).resolve()
assert version("daily-briefing") == daily_briefing.__version__ == "1.1.0"
assert not Path(daily_briefing.__file__).resolve().is_relative_to(source)
starter = files("daily_briefing").joinpath("starter")
assert _starter() == starter  # Installed setup cannot fall back to the checkout.
sdists = list((source / "dist").glob("*.tar.gz"))
assert len(sdists) == 1
with tarfile.open(sdists[0]) as archive:
    prefix = archive.getnames()[0].split("/")[0]
    for path in (source / "template").rglob("*"):
        if path.is_file():
            relative = path.relative_to(source / "template").as_posix()
            assert starter.joinpath(relative).read_bytes() == path.read_bytes(), relative
            member = archive.extractfile(f"{prefix}/template/{relative}")
            assert member is not None and member.read() == path.read_bytes(), relative

with TemporaryDirectory() as temporary:
    root = Path(temporary) / "starter"
    shutil.copytree(str(starter), root)
    help_result = subprocess.run(
        ["daily-briefing", "--help"], cwd=temporary, check=True, capture_output=True, text=True
    )
    assert all(command in help_result.stdout for command in ("init", "try", "publish", "validate"))
    subprocess.run(["daily-briefing", "validate", "--dir", str(root)], cwd=temporary, check=True)
print("Installed CLI, starter resources, wheel and sdist smoke passed.")
