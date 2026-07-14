"""Dynamic, dependency-free installer for NCBI sra-tools.

Downloads the ``current`` sratoolkit release (a stable NCBI URL that always
points at the latest build) and extracts it locally -- no sudo, no module
system, no hardcoded version number required.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

#: NCBI always keeps the latest release available at this "current" alias,
#: so we never need to know or update a specific version number.
SRA_TOOLKIT_BASE_URL = "https://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/current"

#: (system, machine) -> sra-tools platform suffix
PLATFORM_MAP = {
    ("Linux", "x86_64"): "ubuntu64",
    ("Linux", "aarch64"): "ubuntu64",  # NCBI ships no dedicated arm64 linux build
    ("Darwin", "x86_64"): "mac64",
    ("Darwin", "arm64"): "mac-arm64",
}

REQUIRED_TOOLS = ("prefetch", "fasterq-dump")


def detect_platform() -> str:
    """Best-effort mapping from the local OS/arch to an sra-tools build name."""
    key = (platform.system(), platform.machine())
    if key in PLATFORM_MAP:
        return PLATFORM_MAP[key]
    raise RuntimeError(
        f"Could not auto-detect a supported sra-tools platform for {key}. "
        "Pass --platform explicitly (one of: ubuntu64, alma_linux64, mac64, mac-arm64)."
    )


def find_existing_bin(install_dir: Path) -> Optional[Path]:
    """Return the bin/ directory of an already-installed sra-tools, if any."""
    if not install_dir.exists():
        return None
    for bin_dir in sorted(install_dir.glob("*/bin")):
        if all((bin_dir / tool).exists() for tool in REQUIRED_TOOLS):
            return bin_dir
    return None


def install(install_dir: Path, platform_name: Optional[str] = None, force: bool = False) -> Path:
    """Ensure sra-tools is installed under ``install_dir``; return its bin/ path.

    Safe to call repeatedly: if a working install is already present, the
    download is skipped unless ``force=True``.
    """
    install_dir = Path(install_dir)
    install_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing = find_existing_bin(install_dir)
        if existing is not None:
            print(f"[sra-array] sra-tools already installed at {existing}", file=sys.stderr)
            return existing

    plat = platform_name or detect_platform()
    url = f"{SRA_TOOLKIT_BASE_URL}/sratoolkit.current-{plat}.tar.gz"
    print(f"[sra-array] Downloading sra-tools ({plat}) from {url}", file=sys.stderr)

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        urllib.request.urlretrieve(url, tmp_path)  # noqa: S310 - trusted NCBI URL
        print("[sra-array] Extracting ...", file=sys.stderr)
        with tarfile.open(tmp_path) as tf:
            tf.extractall(install_dir)  # noqa: S202 - official NCBI archive
    finally:
        tmp_path.unlink(missing_ok=True)

    bin_dir = find_existing_bin(install_dir)
    if bin_dir is None:
        raise RuntimeError(
            f"sra-tools install failed: no {REQUIRED_TOOLS} found under {install_dir}"
        )

    print(f"[sra-array] Installed at {bin_dir}", file=sys.stderr)
    try:
        subprocess.run([str(bin_dir / "prefetch"), "--version"], check=False)
    except OSError:
        pass

    return bin_dir


def ensure_on_path(bin_dir: Path) -> None:
    """Prepend/append ``bin_dir`` to PATH for the current process (and children)."""
    import os

    current = os.environ.get("PATH", "")
    parts = current.split(":") if current else []
    if str(bin_dir) not in parts:
        os.environ["PATH"] = f"{current}:{bin_dir}" if current else str(bin_dir)


def which_or_install(tools_dir: Path, force: bool = False) -> Path:
    """Return a working sra-tools bin/ dir, checking PATH first, then installing.

    Uses an ``flock`` lock file around the install step so that if many
    SLURM array tasks start at once and none of them find sra-tools yet,
    only one actually downloads it while the rest wait and then reuse it.
    """
    if not force and all(shutil.which(tool) for tool in REQUIRED_TOOLS):
        # Already usable via PATH (e.g. a module load in the calling shell).
        return Path(shutil.which("prefetch")).parent

    tools_dir = Path(tools_dir)
    existing = None if force else find_existing_bin(tools_dir)
    if existing is not None:
        ensure_on_path(existing)
        return existing

    tools_dir.mkdir(parents=True, exist_ok=True)
    lock_path = tools_dir.parent / f"{tools_dir.name}.installing.lock"
    bin_dir: Optional[Path] = None
    try:
        import fcntl

        with lock_path.open("w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                # Re-check now that we hold the lock -- another process may
                # have finished installing while we were waiting for it.
                bin_dir = None if force else find_existing_bin(tools_dir)
                if bin_dir is None:
                    bin_dir = install(tools_dir, force=force)
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
    except ImportError:
        # fcntl is POSIX-only; fall back to an unlocked install on other platforms.
        bin_dir = install(tools_dir, force=force)

    ensure_on_path(bin_dir)
    return bin_dir
