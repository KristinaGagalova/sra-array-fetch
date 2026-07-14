"""Per-accession worker: download one SRA run, convert it to FASTQ, compress it.

This is what actually runs inside each SLURM array task (invoked via
``sra-array run-task``). It is plain Python + subprocess calls to
``prefetch``/``fasterq-dump``, so it can also be run directly on a login
node for local testing of a single accession (pass ``--task-id``).
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from . import installer


def get_accession(ids_file: Path, line_number: int) -> str:
    """Return the accession on the given 1-indexed line of ``ids_file``."""
    with Path(ids_file).open() as fh:
        for i, line in enumerate(fh, start=1):
            if i == line_number:
                acc = line.strip()
                if not acc:
                    raise ValueError(f"Line {line_number} of {ids_file} is empty")
                return acc
    raise ValueError(f"{ids_file} has fewer than {line_number} non-empty lines")


def _compress_fastqs(fastqs: list[Path], threads: int) -> None:
    pigz = shutil.which("pigz")
    if pigz:
        subprocess.run([pigz, "-p", str(threads), *[str(f) for f in fastqs]], check=True)
        return
    for f in fastqs:
        with f.open("rb") as fin, gzip.open(f"{f}.gz", "wb") as fout:
            shutil.copyfileobj(fin, fout)
        f.unlink()


def run(
    ids_file: Path,
    outdir: Path,
    sra_cache: Path,
    tools_dir: Path,
    max_size: str = "100G",
    threads: Optional[int] = None,
    task_id: Optional[int] = None,
) -> None:
    """Download + convert + compress the accession for this array task."""
    ids_file = Path(ids_file)
    outdir = Path(outdir)
    sra_cache = Path(sra_cache)
    tools_dir = Path(tools_dir)

    task_id = task_id or int(os.environ.get("SLURM_ARRAY_TASK_ID", "0") or 0)
    if not task_id:
        raise RuntimeError(
            "No task id given and SLURM_ARRAY_TASK_ID is not set. "
            "Submit this via `sra-array submit` (which sets --array for you), "
            "or pass --task-id to test a single accession locally."
        )
    threads = threads or int(os.environ.get("SLURM_CPUS_PER_TASK", "4") or 4)

    outdir.mkdir(parents=True, exist_ok=True)
    sra_cache.mkdir(parents=True, exist_ok=True)

    srr = get_accession(ids_file, task_id)
    print(f"[sra-array] Task {task_id}: {srr}")
    print(f"[sra-array] OUTDIR={outdir}")
    print(f"[sra-array] SRACACHE={sra_cache}")

    bin_dir = installer.which_or_install(tools_dir)
    prefetch = str(bin_dir / "prefetch")
    fasterq_dump = str(bin_dir / "fasterq-dump")
    print(f"[sra-array] Using prefetch={prefetch}")
    print(f"[sra-array] Using fasterq-dump={fasterq_dump}")

    # Step 1: download the .sra file
    subprocess.run(
        [prefetch, srr, "--output-directory", str(sra_cache), "--max-size", max_size],
        check=True,
    )

    # Step 2: convert to FASTQ
    subprocess.run(
        [
            fasterq_dump,
            str(sra_cache / srr),
            "--split-files",
            "--threads", str(threads),
            "--outdir", str(outdir),
            "--temp", str(sra_cache),
            "--progress",
        ],
        check=True,
    )

    # Step 3: compress
    fastqs = sorted(outdir.glob(f"{srr}_*.fastq"))
    if not fastqs:
        print(f"[sra-array] WARNING: no FASTQ files found for {srr} in {outdir}", file=sys.stderr)
    else:
        _compress_fastqs(fastqs, threads)

    print(f"[sra-array] FASTQ files saved in: {outdir}")
    for f in sorted(outdir.glob(f"{srr}*")):
        print(" ", f)
    print(f"[sra-array] Done: {srr}")
