"""Render the SLURM array batch script and submit it via ``sbatch``.

The job array's size is computed dynamically from the number of accessions
in the ``--ids`` file, so it never needs to be updated by hand as the list
grows or shrinks.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional, Union

TEMPLATE_PATH = Path(__file__).parent / "templates" / "worker.slurm.j2"


def count_accessions(ids_file: Path) -> int:
    """Count non-empty lines (accessions) in the ID list."""
    with Path(ids_file).open() as fh:
        return sum(1 for line in fh if line.strip())


def compute_array_range(
    ids_file: Path,
    start: Optional[int] = None,
    end: Optional[int] = None,
    throttle: Optional[int] = None,
) -> tuple[str, int]:
    """Return (array_range_string, total_accession_count).

    ``start``/``end`` default to the full 1..N range found in ``ids_file``.
    ``end`` is clamped down to N with a warning if it exceeds it.
    """
    total = count_accessions(ids_file)
    if total == 0:
        raise ValueError(f"No accessions found in {ids_file}")

    start = start or 1
    end = end or total
    if end > total:
        print(
            f"[sra-array] WARNING: --end={end} exceeds {total} accessions in "
            f"{ids_file}; clamping to {total}.",
            file=sys.stderr,
        )
        end = total
    if start < 1 or start > end:
        raise ValueError(f"Invalid range: start={start}, end={end} (total={total})")

    array_range = f"{start}-{end}"
    if throttle:
        array_range += f"%{throttle}"
    return array_range, total


def render_script(
    *,
    job_name: str,
    account: str,
    array_range: str,
    cpus: int,
    mem: str,
    walltime: str,
    log_dir: Path,
    ids_file: Path,
    outdir: Path,
    sra_cache: Path,
    tools_dir: Path,
    max_size: str,
    python_exe: str,
) -> str:
    """Fill in the SLURM template using plain string substitution.

    Deliberately avoids f-string/``str.format``/``string.Template`` style
    interpolation here: the generated script is bash, which uses ``$`` and
    ``{}`` constantly, so templating with unique ``__TOKEN__`` markers and
    ``str.replace`` sidesteps any collision entirely.
    """
    template = TEMPLATE_PATH.read_text()
    replacements = {
        "__JOB_NAME__": job_name,
        "__ACCOUNT__": account,
        "__ARRAY_RANGE__": array_range,
        "__CPUS__": str(cpus),
        "__MEM__": mem,
        "__WALLTIME__": walltime,
        "__LOG_DIR__": str(log_dir),
        "__PYTHON__": python_exe,
        "__IDS__": str(ids_file),
        "__OUTDIR__": str(outdir),
        "__SRACACHE__": str(sra_cache),
        "__TOOLS_DIR__": str(tools_dir),
        "__MAX_SIZE__": max_size,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def submit(
    *,
    ids_file: Path,
    outdir: Path,
    sra_cache: Path,
    tools_dir: Path,
    account: str,
    job_name: str = "sra_array",
    start: Optional[int] = None,
    end: Optional[int] = None,
    throttle: Optional[int] = None,
    cpus: int = 8,
    mem: str = "16G",
    walltime: str = "12:00:00",
    max_size: str = "100G",
    log_dir: Optional[Path] = None,
    python_exe: str = "python3",
    dry_run: bool = False,
) -> Union[subprocess.CompletedProcess, str]:
    """Generate the batch script and submit it with ``sbatch`` (unless dry_run)."""
    ids_file = Path(ids_file)
    outdir = Path(outdir)
    sra_cache = Path(sra_cache)
    tools_dir = Path(tools_dir)

    array_range, total = compute_array_range(ids_file, start=start, end=end, throttle=throttle)

    log_dir = Path(log_dir) if log_dir else (outdir / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)
    sra_cache.mkdir(parents=True, exist_ok=True)

    script = render_script(
        job_name=job_name,
        account=account,
        array_range=array_range,
        cpus=cpus,
        mem=mem,
        walltime=walltime,
        log_dir=log_dir,
        ids_file=ids_file,
        outdir=outdir,
        sra_cache=sra_cache,
        tools_dir=tools_dir,
        max_size=max_size,
        python_exe=python_exe,
    )

    script_path = log_dir / f"{job_name}.generated.slurm"
    script_path.write_text(script)
    script_path.chmod(0o755)

    print(f"[sra-array] {total} accessions found in {ids_file}")
    print(f"[sra-array] Array range: {array_range}")
    print(f"[sra-array] Generated batch script: {script_path}")

    if dry_run:
        print("[sra-array] --dry-run set; not submitting. Inspect or run the script above manually.")
        return str(script_path)

    if not shutil_which("sbatch"):
        raise RuntimeError(
            "sbatch not found on PATH. Run this from a SLURM login/submit node, "
            "or use --dry-run to just generate the script."
        )

    return subprocess.run(["sbatch", str(script_path)], check=True)


def shutil_which(name: str) -> Optional[str]:
    import shutil

    return shutil.which(name)
