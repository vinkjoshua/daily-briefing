"""Fetch verified, pinned CLI packages into a private versioned cache."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

VERSIONS = {"codex": "0.160.0", "gh": "2.102.0"}
ASSETS = {
    ("codex", "Darwin", "arm64"): (
        "https://github.com/openai/codex/releases/download/rust-v0.160.0/codex-package-aarch64-apple-darwin.tar.gz",
        "007df41b607dbbc8d204b9746ce7fed2d4ce6c813f44c32ceee54175ca796525",
    ),
    ("codex", "Linux", "arm64"): (
        "https://github.com/openai/codex/releases/download/rust-v0.160.0/codex-package-aarch64-unknown-linux-musl.tar.gz",
        "7f0fe42ff22ecfa3a47bc4a34f5b22c4218b431a4ec0aba51c7d98299f07900c",
    ),
    ("codex", "Darwin", "amd64"): (
        "https://github.com/openai/codex/releases/download/rust-v0.160.0/codex-package-x86_64-apple-darwin.tar.gz",
        "4d50514b2d8acd81ca8cfee55b667b3dc4f7681b65bf3299ff06b11a064f8861",
    ),
    ("codex", "Linux", "amd64"): (
        "https://github.com/openai/codex/releases/download/rust-v0.160.0/codex-package-x86_64-unknown-linux-musl.tar.gz",
        "4fcc47ab57f52ff75363951a8761146cd10c8288bd86fed45487dbb204a16b71",
    ),
    ("gh", "Linux", "amd64"): (
        "https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_linux_amd64.tar.gz",
        "bb766f710eef8ede859c18578c72c327597cd4c8a85b06001b1f3843c6019386",
    ),
    ("gh", "Linux", "arm64"): (
        "https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_linux_arm64.tar.gz",
        "7862c86c72f43df3a2d93ddde6f473285b4e2af61b494849846827e513ef6484",
    ),
    ("gh", "Darwin", "amd64"): (
        "https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_macOS_amd64.zip",
        "b245f24eb2bf5f75b426b4c26da3651a107f8d5b6f4fddfbfccc5679041378b3",
    ),
    ("gh", "Darwin", "arm64"): (
        "https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_macOS_arm64.zip",
        "da922c20d1792e5b2cbf375593d7a658acf034c12c84e007e71c76ef959c337e",
    ),
}


class BootstrapError(RuntimeError):
    """A CLI package could not be installed safely."""


def _matches(binary: Path, name: str) -> bool:
    """Check an executable's exact pinned version without printing its output."""
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return False
    try:
        result = subprocess.run(
            [str(binary), "--version"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False
    prefix = "codex-cli " if name == "codex" else "gh version "
    first = (result.stdout or "").splitlines()
    return bool(
        result.returncode == 0
        and first
        and first[0].startswith(prefix)
        and first[0][len(prefix) :].split()[:1] == [VERSIONS[name]]
    )


def _safe_path(root: Path, name: str) -> Path:
    """Reject any archive member that can escape the temporary package."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise BootstrapError("Unsafe path in CLI package archive.")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise BootstrapError("Unsafe path in CLI package archive.")
    return target


def _extract(archive: Path, destination: Path, zipped: bool) -> None:
    """Extract regular files and directories only, preserving their relative paths."""
    if zipped:
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                _safe_path(destination, member.filename)
                kind = (member.external_attr >> 16) & 0o170000
                if kind not in (0, 0o100000, 0o040000):
                    raise BootstrapError("Unsafe link or special member in CLI package archive.")
            for member in package.infolist():
                target = _safe_path(destination, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(member) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(((member.external_attr >> 16) & 0o777) or 0o644)
    else:
        with tarfile.open(archive, "r:gz") as package:
            members = package.getmembers()
            for member in members:
                _safe_path(destination, member.name)
                if not (member.isfile() or member.isdir()):
                    raise BootstrapError("Unsafe link or special member in CLI package archive.")
            for member in members:
                target = _safe_path(destination, member.name)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = package.extractfile(member)
                    if source is None:
                        raise BootstrapError("Unreadable file in CLI package archive.")
                    with source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(member.mode & 0o777)


def ensure_tool(name: str) -> Path:
    """Return an exact matching PATH executable or install the official pinned package.

    Args:
        name: Either ``codex`` or ``gh``.

    Returns:
        Path to the executable; companion files remain beside it in the cache.

    Raises:
        BootstrapError: Unsupported platform, failed download, or invalid package.
    """
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    key = (name, system, arch)
    if key not in ASSETS:
        raise BootstrapError(f"Unsupported tool or platform: {name} on {system}/{machine}.")
    if installed := shutil.which(name):
        binary = Path(installed)
        if _matches(binary, name):
            return binary

    url, digest = ASSETS[key]
    filename = url.rsplit("/", 1)[1]
    zipped = filename.endswith(".zip")
    relative = (
        Path("bin/codex")
        if name == "codex"
        else Path(filename.removesuffix(".zip").removesuffix(".tar.gz"), "bin", "gh")
    )
    if cache_env := os.environ.get("XDG_CACHE_HOME"):
        cache_home = Path(cache_env)
    else:
        cache_home = Path.home() / ("Library/Caches" if system == "Darwin" else ".cache")
    parent = cache_home / "daily-briefing" / "tools"
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent.chmod(0o700)
        cache = parent / f"{name}-{VERSIONS[name]}-{system}-{arch}"
        binary = cache / relative
        if _matches(binary, name):
            return binary
        if cache.exists():
            shutil.rmtree(cache)
    except OSError:
        raise BootstrapError(
            f"Could not prepare the {name} cache; check cache permissions."
        ) from None
    print(f"Downloading {name} {VERSIONS[name]}…", file=sys.stderr)
    try:
        with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=parent) as temporary:
            staging = Path(temporary)
            archive = staging / filename
            with urllib.request.urlopen(url, timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            with archive.open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != digest:
                raise BootstrapError(f"SHA256 checksum mismatch for {name}; retry the download.")
            package = staging / "package"
            package.mkdir(mode=0o700)
            _extract(archive, package, zipped)
            if not _matches(package / relative, name):
                raise BootstrapError(
                    f"The downloaded {name} executable has an invalid version or mode."
                )
            package.rename(cache)
    except (
        OSError,
        urllib.error.URLError,
        tarfile.TarError,
        zipfile.BadZipFile,
        EOFError,
    ) as error:
        raise BootstrapError(
            f"Could not download or unpack {name} {VERSIONS[name]}; check your connection "
            f"and cache permissions, then retry ({type(error).__name__})."
        ) from None
    return binary
