import hashlib
import io
import os
import tarfile
import zipfile
from urllib.error import URLError

import pytest

from daily_briefing import bootstrap as bootstrap_module


@pytest.fixture
def bootstrap(monkeypatch, tmp_path):
    module = bootstrap_module
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache with spaces"))
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(module.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    return module


def archive(name, suffix, members=None, gh_root="gh_2.102.0_linux_amd64"):
    version = "0.160.0" if name == "codex" else "2.102.0"
    script = (
        f"#!/bin/sh\nprintf '{'codex-cli' if name == 'codex' else 'gh version'} {version}\\n'\n"
    )
    root = "" if name == "codex" else gh_root + "/"
    members = members or [(f"{root}bin/{name}", script.encode(), 0o755)]
    stream = io.BytesIO()
    if suffix == ".zip":
        with zipfile.ZipFile(stream, "w") as zf:
            for path, content, mode in members:
                info = zipfile.ZipInfo(path)
                info.external_attr = (0o100000 | mode) << 16
                zf.writestr(info, content)
    else:
        with tarfile.open(fileobj=stream, mode="w:gz") as tf:
            for path, content, mode in members:
                info = tarfile.TarInfo(path)
                info.size, info.mode = len(content), mode
                tf.addfile(info, io.BytesIO(content))
    return stream.getvalue()


def download_fixture(monkeypatch, bootstrap, payload):
    # Only the network is replaced; checksums, extraction, execution and cache are real.
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload))
    monkeypatch.setattr(
        bootstrap,
        "ASSETS",
        {
            key: (url, hashlib.sha256(payload).hexdigest())
            for key, (url, digest) in bootstrap.ASSETS.items()
        },
    )


@pytest.mark.parametrize("name", ["codex", "gh"])
@pytest.mark.parametrize("system", ["Darwin", "Linux"])
@pytest.mark.parametrize("machine", ["x86_64", "arm64"])
def test_installs_pinned_package_and_reuses_cache(bootstrap, monkeypatch, name, system, machine):
    monkeypatch.setattr(bootstrap.platform, "system", lambda: system)
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: machine)
    suffix = ".zip" if name == "gh" and system == "Darwin" else ".tar.gz"
    gh_system = "macOS" if system == "Darwin" else "linux"
    gh_arch = "amd64" if machine == "x86_64" else "arm64"
    gh_root = f"gh_2.102.0_{gh_system}_{gh_arch}"
    payload = archive(name, suffix, gh_root=gh_root)
    download_fixture(monkeypatch, bootstrap, payload)
    binary = bootstrap.ensure_tool(name)
    assert binary.is_file() and os.access(binary, os.X_OK)
    assert "cache with spaces" in str(binary)
    monkeypatch.setattr(
        bootstrap.urllib.request, "urlopen", lambda *a, **k: pytest.fail("redownload")
    )
    assert bootstrap.ensure_tool(name) == binary


def test_codex_companion_and_relative_files_are_preserved(bootstrap, monkeypatch):
    payload = archive(
        "codex",
        ".tar.gz",
        [
            ("bin/codex", b"#!/bin/sh\necho codex-cli 0.160.0\n", 0o755),
            ("bin/codex-code-mode-host", b"#!/bin/sh\necho companion\n", 0o755),
            ("codex-resources/package.txt", b"package data", 0o644),
            ("codex-path/rg", b"#!/bin/sh\necho rg\n", 0o755),
            ("codex-package.json", b'{"entrypoint":"bin/codex"}', 0o644),
        ],
    )
    download_fixture(monkeypatch, bootstrap, payload)
    binary = bootstrap.ensure_tool("codex")
    assert os.access(binary.with_name("codex-code-mode-host"), os.X_OK)
    root = binary.parent.parent
    assert (root / "codex-resources/package.txt").read_bytes() == b"package data"
    assert os.access(root / "codex-path/rg", os.X_OK)
    assert (root / "codex-package.json").read_bytes() == b'{"entrypoint":"bin/codex"}'


@pytest.mark.parametrize("name", ["codex", "gh"])
def test_exact_path_version_is_reused(bootstrap, monkeypatch, tmp_path, name):
    binary = tmp_path / name
    version = "codex-cli 0.160.0" if name == "codex" else "gh version 2.102.0 (2026-10-06)"
    binary.write_text(f"#!/bin/sh\necho '{version}'\n")
    binary.chmod(0o755)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(binary))
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    assert bootstrap.ensure_tool(name) == binary


def test_wrong_path_version_downloads_pinned_release(bootstrap, monkeypatch, tmp_path):
    binary = tmp_path / "codex"
    binary.write_text("#!/bin/sh\necho codex-cli 0.160.01\n")
    binary.chmod(0o755)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: str(binary))
    download_fixture(monkeypatch, bootstrap, archive("codex", ".tar.gz"))
    assert bootstrap.ensure_tool("codex") != binary


@pytest.mark.parametrize("system,machine", [("Windows", "AMD64"), ("Linux", "riscv64")])
def test_unsupported_platform_fails_before_network(bootstrap, monkeypatch, system, machine):
    monkeypatch.setattr(bootstrap.platform, "system", lambda: system)
    monkeypatch.setattr(bootstrap.platform, "machine", lambda: machine)
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(bootstrap.BootstrapError, match="[Uu]nsupported"):
        bootstrap.ensure_tool("gh")


def test_unknown_tool_fails_before_network(bootstrap, monkeypatch):
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(bootstrap.BootstrapError, match="[Uu]nsupported|[Uu]nknown"):
        bootstrap.ensure_tool("npm")


def test_digest_mismatch_does_not_leave_reusable_cache(bootstrap, monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"corrupt"))
    with pytest.raises(bootstrap.BootstrapError, match="SHA256|checksum"):
        bootstrap.ensure_tool("gh")
    assert not list((tmp_path / "cache with spaces").rglob("gh"))
    download_fixture(monkeypatch, bootstrap, archive("gh", ".tar.gz"))
    assert bootstrap.ensure_tool("gh").is_file()


@pytest.mark.parametrize("path", ["../escaped", "/tmp/escaped", "package/../../escaped"])
@pytest.mark.parametrize("suffix", [".tar.gz", ".zip"])
def test_archive_traversal_is_rejected(bootstrap, monkeypatch, tmp_path, path, suffix):
    if suffix == ".zip":
        monkeypatch.setattr(bootstrap.platform, "system", lambda: "Darwin")
    download_fixture(monkeypatch, bootstrap, archive("gh", suffix, [(path, b"bad", 0o755)]))
    with pytest.raises(bootstrap.BootstrapError, match="[Uu]nsafe"):
        bootstrap.ensure_tool("gh")
    assert not (tmp_path / "escaped").exists()
    assert not list((tmp_path / "cache with spaces").rglob("escaped"))


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_tar_links_and_special_members_are_rejected(bootstrap, monkeypatch, kind):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tf:
        info = tarfile.TarInfo("gh")
        info.type, info.linkname = kind, "../../escape"
        tf.addfile(info)
    download_fixture(monkeypatch, bootstrap, stream.getvalue())
    with pytest.raises(bootstrap.BootstrapError, match="[Uu]nsafe"):
        bootstrap.ensure_tool("gh")


def test_zip_symlink_is_rejected(bootstrap, monkeypatch):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        info = zipfile.ZipInfo("gh")
        info.external_attr = 0o120777 << 16
        zf.writestr(info, "../../escape")
    monkeypatch.setattr(bootstrap.platform, "system", lambda: "Darwin")
    download_fixture(monkeypatch, bootstrap, stream.getvalue())
    with pytest.raises(bootstrap.BootstrapError, match="[Uu]nsafe"):
        bootstrap.ensure_tool("gh")


def test_download_error_is_actionable(bootstrap, monkeypatch):
    def offline(*a, **k):
        raise URLError("offline")

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", offline)
    with pytest.raises(bootstrap.BootstrapError, match="[Dd]ownload.*gh|gh.*[Dd]ownload"):
        bootstrap.ensure_tool("gh")


def test_cancelled_download_cleans_temporary_files(bootstrap, monkeypatch, tmp_path):
    def cancelled(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(bootstrap.urllib.request, "urlopen", cancelled)
    with pytest.raises(KeyboardInterrupt):
        bootstrap.ensure_tool("gh")
    cache = tmp_path / "cache with spaces"
    assert not [p for p in cache.rglob("*") if p.is_file()]


@pytest.mark.parametrize(
    "content,mode", [(b"#!/bin/sh\necho gh version 1.0\n", 0o755), (b"not an executable", 0o644)]
)
def test_invalid_downloaded_executable_is_not_cached(
    bootstrap, monkeypatch, tmp_path, content, mode
):
    download_fixture(
        monkeypatch,
        bootstrap,
        archive("gh", ".tar.gz", [("gh_2.102.0_linux_amd64/bin/gh", content, mode)]),
    )
    with pytest.raises(bootstrap.BootstrapError, match="executable|version"):
        bootstrap.ensure_tool("gh")
    assert not list((tmp_path / "cache with spaces").rglob("gh"))


def test_corrupt_cached_executable_is_replaced(bootstrap, monkeypatch):
    download_fixture(monkeypatch, bootstrap, archive("gh", ".tar.gz"))
    binary = bootstrap.ensure_tool("gh")
    binary.write_text("#!/bin/sh\necho gh version 1.0\n")
    assert bootstrap.ensure_tool("gh") == binary
    assert "2.102.0" in binary.read_text()


def test_unusable_cache_location_is_actionable(bootstrap, monkeypatch, tmp_path):
    cache = tmp_path / "cache-file"
    cache.write_text("not a directory")
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    with pytest.raises(bootstrap.BootstrapError, match="cache"):
        bootstrap.ensure_tool("gh")
