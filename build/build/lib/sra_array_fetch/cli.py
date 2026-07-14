"""Command-line interface for sra-array-fetch.

Three subcommands:

  sra-array install     Download sra-tools locally (optional -- happens
                         automatically on first use otherwise).
  sra-array submit      Compute the array size from an accession list and
                         submit the SLURM job array.
  sra-array run-task    Process a single accession. This is what the
                         generated SLURM script calls per array task; it can
                         also be run directly (with --task-id) to test one
                         accession on a login node before submitting.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from . import installer, worker
from . import submit as submit_mod


def _add_install_parser(subparsers):
    p = subparsers.add_parser("install", help="Download and install sra-tools locally.")
    p.add_argument(
        "--dir", type=Path, default=Path.home() / "tools" / "sra-tools",
        help="Install directory (default: ~/tools/sra-tools)",
    )
    p.add_argument(
        "--platform", default=None,
        help="ubuntu64 | alma_linux64 | mac64 | mac-arm64 (default: auto-detect)",
    )
    p.add_argument("--force", action="store_true", help="Re-download even if already installed.")
    return p


def _add_submit_parser(subparsers):
    p = subparsers.add_parser("submit", help="Submit the SLURM array job.")
    p.add_argument("--ids", required=True, type=Path, help="Path to the SRR accession list (one per line).")
    p.add_argument("--outdir", required=True, type=Path, help="Directory to write FASTQ files into.")
    p.add_argument(
        "--sra-cache", type=Path, default=None,
        help="Directory for .sra downloads (default: <outdir>/../sra_cache).",
    )
    p.add_argument(
        "--tools-dir", type=Path, default=Path.home() / "tools" / "sra-tools",
        help="Where sra-tools is (or will be) installed (default: ~/tools/sra-tools).",
    )
    p.add_argument("--account", required=True, help="SLURM account to charge.")
    p.add_argument("--job-name", default="sra_array")
    p.add_argument("--start", type=int, default=None, help="First line of --ids to process (default: 1).")
    p.add_argument("--end", type=int, default=None, help="Last line of --ids to process (default: last line).")
    p.add_argument("--throttle", type=int, default=None, help="Max concurrent array tasks, e.g. 20.")
    p.add_argument("--cpus", type=int, default=8, help="cpus-per-task (default: 8).")
    p.add_argument("--mem", default="16G", help="Memory per task (default: 16G).")
    p.add_argument("--time", dest="walltime", default="12:00:00", help="Walltime (default: 12:00:00).")
    p.add_argument("--max-size", default="100G", help="Max .sra download size passed to prefetch.")
    p.add_argument("--python", default=sys.executable, help="Python interpreter to invoke on compute nodes.")
    p.add_argument("--dry-run", action="store_true", help="Generate the batch script but do not submit it.")
    return p


def _add_run_task_parser(subparsers):
    p = subparsers.add_parser(
        "run-task",
        help="Download+convert+compress one accession (called by the SLURM array task).",
    )
    p.add_argument("--ids", required=True, type=Path)
    p.add_argument("--outdir", required=True, type=Path)
    p.add_argument("--sra-cache", required=True, type=Path)
    p.add_argument("--tools-dir", required=True, type=Path)
    p.add_argument("--max-size", default="100G")
    p.add_argument(
        "--task-id", type=int, default=None,
        help="Override SLURM_ARRAY_TASK_ID -- use this to test a single accession locally.",
    )
    p.add_argument("--threads", type=int, default=None, help="Override SLURM_CPUS_PER_TASK.")
    return p


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="sra-array",
        description=(
            "Download SRA runs and convert them to FASTQ as a dynamically-sized "
            "SLURM job array, with self-installing sra-tools."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_install_parser(subparsers)
    _add_submit_parser(subparsers)
    _add_run_task_parser(subparsers)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "install":
        installer.install(args.dir, platform_name=args.platform, force=args.force)
        return 0

    if args.command == "submit":
        sra_cache = args.sra_cache or (args.outdir.parent / "sra_cache")
        submit_mod.submit(
            ids_file=args.ids,
            outdir=args.outdir,
            sra_cache=sra_cache,
            tools_dir=args.tools_dir,
            account=args.account,
            job_name=args.job_name,
            start=args.start,
            end=args.end,
            throttle=args.throttle,
            cpus=args.cpus,
            mem=args.mem,
            walltime=args.walltime,
            max_size=args.max_size,
            python_exe=args.python,
            dry_run=args.dry_run,
        )
        return 0

    if args.command == "run-task":
        worker.run(
            ids_file=args.ids,
            outdir=args.outdir,
            sra_cache=args.sra_cache,
            tools_dir=args.tools_dir,
            max_size=args.max_size,
            threads=args.threads,
            task_id=args.task_id,
        )
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
