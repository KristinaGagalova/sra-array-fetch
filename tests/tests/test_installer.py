from pathlib import Path

import pytest

from sra_array_fetch import installer


def _make_bin(tmp_path: Path, version: str, tools=("prefetch", "fasterq-dump")) -> Path:
    bin_dir = tmp_path / f"sratoolkit.{version}-ubuntu64" / "bin"
    bin_dir.mkdir(parents=True)
    for tool in tools:
        (bin_dir / tool).write_text("#!/bin/sh\necho fake\n")
        (bin_dir / tool).chmod(0o755)
    return bin_dir


def test_find_existing_bin_missing_dir(tmp_path):
    assert installer.find_existing_bin(tmp_path / "nope") is None


def test_find_existing_bin_empty_dir(tmp_path):
    assert installer.find_existing_bin(tmp_path) is None


def test_find_existing_bin_found(tmp_path):
    bin_dir = _make_bin(tmp_path, "3.4.1")
    assert installer.find_existing_bin(tmp_path) == bin_dir


def test_find_existing_bin_ignores_incomplete_install(tmp_path):
    # Only prefetch present, fasterq-dump missing -> should not count.
    _make_bin(tmp_path, "3.4.1", tools=("prefetch",))
    assert installer.find_existing_bin(tmp_path) is None


def test_install_skips_download_when_already_present(tmp_path, monkeypatch):
    _make_bin(tmp_path, "3.4.1")

    def _boom(*args, **kwargs):
        raise AssertionError("download should not have been attempted")

    monkeypatch.setattr(installer.urllib.request, "urlretrieve", _boom)
    result = installer.install(tmp_path)
    assert result == installer.find_existing_bin(tmp_path)


def test_detect_platform_known(monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    assert installer.detect_platform() == "ubuntu64"


def test_detect_platform_unknown(monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Plan9")
    monkeypatch.setattr(installer.platform, "machine", lambda: "weird")
    with pytest.raises(RuntimeError):
        installer.detect_platform()


def test_ensure_on_path_appends_once(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", "/usr/bin")
    installer.ensure_on_path(tmp_path / "bin")
    import os

    assert str(tmp_path / "bin") in os.environ["PATH"].split(":")
    before = os.environ["PATH"]
    installer.ensure_on_path(tmp_path / "bin")
    assert os.environ["PATH"] == before  # no duplicate append


def test_which_or_install_uses_existing_install_without_downloading(tmp_path, monkeypatch):
    tools_dir = tmp_path / "tools"
    bin_dir = _make_bin(tools_dir, "3.4.1")

    monkeypatch.setattr(installer.shutil, "which", lambda name: None)

    def _boom(*args, **kwargs):
        raise AssertionError("download should not have been attempted")

    monkeypatch.setattr(installer.urllib.request, "urlretrieve", _boom)

    result = installer.which_or_install(tools_dir)
    assert result == bin_dir


def test_which_or_install_uses_path_first(tmp_path, monkeypatch):
    fake_prefetch = tmp_path / "existing_bin" / "prefetch"
    fake_prefetch.parent.mkdir(parents=True)
    fake_prefetch.write_text("#!/bin/sh\n")
    fake_prefetch.chmod(0o755)

    monkeypatch.setattr(
        installer.shutil, "which",
        lambda name: str(fake_prefetch.parent / name) if name in installer.REQUIRED_TOOLS else None,
    )
    result = installer.which_or_install(tmp_path / "unused_tools_dir")
    assert result == fake_prefetch.parent
