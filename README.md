# sra-array-fetch

Download SRA runs and convert them to FASTQ as a **dynamically-sized SLURM
job array**, with **self-installing sra-tools** — no hardcoded `--array=2-279`,
no hardcoded `sratoolkit.3.4.1-ubuntu64` path, no sudo, no module system
required.

Built for HPC clusters (developed against Pawsey/Setonix and NCI Gadi) but
has no Pawsey-specific assumptions baked in.

## What it does

1. **`sra-array install`** — downloads NCBI's `sra-tools` (`prefetch`,
   `fasterq-dump`) from the stable `.../sdk/current/...` URL, which always
   points at the latest release. Skips the download if a working install is
   already present.
2. **`sra-array submit`** — reads your accession list, counts how many
   accessions are in it, and submits a SLURM job array sized exactly to
   match (`--array=1-<N>`). Generates the batch script for you; nothing to
   edit by hand when the list changes.
3. **`sra-array run-task`** — runs inside each array task: resolves this
   task's accession, installs `sra-tools` on first use if it isn't already
   there, runs `prefetch` → `fasterq-dump` → compression (`pigz` if
   available, else `gzip`).

The SLURM batch script itself is a thin generated shim — all real logic
lives in testable Python, not in bash.

## Repository layout

```
sra-array-fetch/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── sra_array_fetch/
│       ├── __init__.py
│       ├── __main__.py        # enables `python -m sra_array_fetch`
│       ├── cli.py             # argparse CLI: install / submit / run-task
│       ├── installer.py       # dynamic sra-tools download/detect/install
│       ├── worker.py          # per-accession download+convert+compress
│       ├── submit.py          # array-size computation + sbatch submission
│       └── templates/
│           └── worker.slurm.j2  # minimal generated SLURM shim
└── tests/
    ├── test_installer.py
    ├── test_submit.py
    └── test_worker.py
```

## Install

Two ways to get this running, depending on your situation. Both are sudo-free.

### Option A — `pip install` (venv, needs some quota)

Best when you have headroom in `$HOME` (or wherever `pip` writes to) and may
want to add dependencies down the line.

```bash
git clone https://github.com/KristinaGagalova/sra-array-fetch.git
cd sra-array-fetch
python3 -m venv ~/envs/sra-array-fetch
source ~/envs/sra-array-fetch/bin/activate
pip install -e .          # or: pip install -e ".[dev]" to also get pytest
```

This installs a `sra-array` console command (via `pyproject.toml`
`[project.scripts]`). No third-party dependencies are required — everything
uses the Python standard library.

Run the test suite:

```bash
pip install -e ".[dev]"
pytest
```

Directly from GitHub, without cloning first:

```bash
pip install git+https://github.com/KristinaGagalova/sra-array-fetch.git
# pin to a tag/commit instead of the default branch:
pip install git+https://github.com/KristinaGagalova/sra-array-fetch.git@v0.1.0
```

**On SLURM job submission:** run `sra-array submit` from *inside* the
activated venv. It records its own `sys.executable` and bakes that exact
interpreter path into the generated batch script, so array tasks
automatically use the right Python with no `module load`/`source activate`
needed inside the SLURM script itself — as long as the venv lives on a
filesystem shared between login and compute nodes (true for `$HOME` and
`$MYSCRATCH` on Pawsey/Gadi).

### Option B — no `pip install` at all (scratch, zero quota impact)

Best when your home directory quota is tight. Because this package has
**zero third-party dependencies**, `pip`/venv machinery isn't actually
required — dropping the source on scratch and pointing `PYTHONPATH` at it is
enough. Footprint is well under 1 MB.

```bash
# clone (or download) straight onto scratch, not home
git clone --depth 1 https://github.com/KristinaGagalova/sra-array-fetch.git \
  "$MYSCRATCH/tools/sra-array-fetch"
```

If `git clone` isn't reachable from your node, a plain archive download works
identically and doesn't need `git` at all:

```bash
curl -L https://github.com/KristinaGagalova/sra-array-fetch/archive/refs/heads/master.tar.gz \
  | tar -xz -C "$MYSCRATCH/tools"
mv "$MYSCRATCH/tools/sra-array-fetch-master" "$MYSCRATCH/tools/sra-array-fetch"
```

Then make the `sra-array` command available, without installing anything:

```bash
# add to ~/.bashrc -- this line itself uses ~0 bytes of quota
export PYTHONPATH="$MYSCRATCH/tools/sra-array-fetch/src:$PYTHONPATH"
alias sra-array="python3 -m sra_array_fetch"
```

```bash
source ~/.bashrc
sra-array --help    # works, nothing written to site-packages anywhere
```

**On SLURM job submission:** the generated batch script falls back to
whatever `python3` resolves to on `$PATH` (rather than a venv path), which
works transparently as long as login and compute nodes share the same base
Python — the normal case on Pawsey/Gadi.

> **Bare system `python3` too old?** HPC login nodes sometimes default to a
> genuinely old system Python (e.g. 3.6) before any module is loaded. This
> package targets Python 3.6+ specifically so Option B keeps working in that
> situation — but if you hit a `SyntaxError` anyway, check which `python3`
> your alias resolves to (`type python3`) and, if needed, `module load
> python/<newer-version>` before sourcing the alias so a more recent
> interpreter is picked up.

**Trade-off:** if you ever add a dependency to this package later, Option B
stops working (`PYTHONPATH` doesn't resolve dependencies) — switch to Option
A's venv at that point, just point it at `$MYSCRATCH/envs/...` instead of
`$HOME` if quota is still a concern.

> **Also watch `--tools-dir`.** Independent of which install option you pick
> above, the downloaded `sra-tools` binaries themselves (not this Python
> package) are a few hundred MB and default to `~/tools/sra-tools`. If home
> quota is tight, always pass `--tools-dir "$MYSCRATCH/tools/sra-tools"`
> to `sra-array submit` / `sra-array install` / `sra-array run-task` to keep
> that off your home directory too.

> **`pip install -e .` fails with "setup.py not found"?** That means your
> pip predates [PEP 660](https://peps.python.org/pep-0660/) (pip < 21.3),
> which is common on HPC default environments (e.g. Setonix ships pip
> 20.0.2). Either upgrade pip first —
> ```bash
> python3 -m pip install --upgrade pip
> pip install -e .
> ```
> — or skip editable mode entirely and just do a regular install, which
> works on any pip version:
> ```bash
> pip install .
> ```
> The only difference: with `-e`, local source edits take effect
> immediately; with a regular install, re-run `pip install .` after pulling
> updates. For normal usage (not developing the package itself), `pip
> install .` is the simpler choice.

## Quick start

```bash
sra-array submit \
  --ids /path/to/SRR_Acc_List.txt \
  --outdir /scratch/pawsey1142/$USER/project/rawFastq \
  --tools-dir /scratch/pawsey1142/$USER/tools/sra-tools \
  --account pawsey1142 \
  --throttle 20
```

That's it — this counts the accessions in `SRR_Acc_List.txt`, generates a
SLURM batch script sized `--array=1-<N>%20`, and submits it with `sbatch`.
`sra-tools` is installed automatically by the first array task that needs it
(see [Compute-node internet access](#compute-node-internet-access) below for
an important caveat on some clusters).

## Commands

### `sra-array install`

Download and install `sra-tools` ahead of time (optional — `submit`/`run-task`
will do this automatically on first use, but it can be useful to pre-install
from a login node, especially if compute nodes lack internet access).

```bash
sra-array install --dir ~/tools/sra-tools
```

| Flag | Default | Description |
|---|---|---|
| `--dir` | `~/tools/sra-tools` | Install directory |
| `--platform` | auto-detected | `ubuntu64` \| `alma_linux64` \| `mac64` \| `mac-arm64` |
| `--force` | off | Re-download even if already installed |

### `sra-array submit`

Compute the array size from the accession list and submit the SLURM job.

```bash
sra-array submit \
  --ids SRR_Acc_List.txt \
  --outdir /scratch/pawsey1142/$USER/rawFastq \
  --account pawsey1142 \
  [--sra-cache DIR] [--tools-dir DIR] [--job-name NAME] \
  [--start N] [--end N] [--throttle N] \
  [--cpus N] [--mem 16G] [--time 12:00:00] [--partition NAME] \
  [--max-size 100G] [--python /path/to/python3] [--dry-run]
```

| Flag | Default | Description |
|---|---|---|
| `--ids` | *(required)* | Accession list, one SRR per line |
| `--outdir` | *(required)* | Where FASTQ files land |
| `--sra-cache` | `<outdir>/../sra_cache` | `.sra` download cache |
| `--tools-dir` | `~/tools/sra-tools` | Where sra-tools is/will be installed |
| `--account` | *(required)* | SLURM account |
| `--job-name` | `sra_array` | SLURM job name |
| `--start` / `--end` | full list | Subrange of the accession list to run (e.g. to resume a partial run) |
| `--throttle` | none | Max concurrent array tasks, e.g. `20` → `--array=1-N%20` |
| `--cpus` | `8` | cpus-per-task |
| `--mem` | `16G` | Memory per task |
| `--time` | `12:00:00` | Walltime |
| `--partition` | account default | SLURM partition — see [Compute-node internet access](#compute-node-internet-access) below, this is usually required |
| `--max-size` | `100G` | Max `.sra` size passed to `prefetch` |
| `--python` | current interpreter | Python invoked on compute nodes — make sure it's reachable there |
| `--dry-run` | off | Only generate the batch script, don't submit |

The generated script is written to `<outdir>/logs/<job-name>.generated.slurm`
so you can inspect or resubmit it directly with `sbatch` if you want.

### `sra-array run-task`

What each array task runs. You normally don't call this directly — but it's
plain Python, so you can test a single accession on a login node first:

```bash
sra-array run-task \
  --ids SRR_Acc_List.txt \
  --outdir /tmp/test_out \
  --sra-cache /tmp/test_cache \
  --tools-dir ~/tools/sra-tools \
  --task-id 1
```

`--task-id` overrides `SLURM_ARRAY_TASK_ID` for local testing; inside a real
array job SLURM sets that env var for you and `--task-id` can be omitted.

## Compute-node internet access

Many HPC clusters (Setonix included) route outbound internet access only
through login nodes or a dedicated data-transfer partition — **not** the
general-purpose compute partition. This matters here because `prefetch`
needs to reach NCBI *at the moment it runs*, not just at install time — so
pre-installing `sra-tools` from a login node does **not** fix it on its own;
jobs submitted to the default compute partition will fail (or succeed only
intermittently, e.g. if a couple of tasks happen to land on a node with
transient connectivity) with an error like:

```
int: connection not found while validating within network system module
```

**Fix: submit to the cluster's data-transfer partition.** On Pawsey/Setonix
this is the `copy` partition:

```bash
sra-array submit \
  --ids SRR_Acc_List.txt \
  --outdir /scratch/pawsey1142/$USER/rawFastq \
  --account pawsey1142 \
  --partition copy \
  --cpus 2 --mem 4G \
  --throttle 8
```

The `copy` partition is intended for lightweight data-movement jobs rather
than heavy compute, so it's typically resource-constrained — check
`sinfo -p copy` (or your cluster's equivalent) for the actual per-node
CPU/memory limits and adjust `--cpus`/`--mem`/`--throttle` down accordingly
rather than assuming the same values you'd use on the compute partition.
Other clusters may name their internet-enabled partition differently (e.g.
`dtn`, `xfer`) — check your site's documentation.

If your cluster doesn't have a separate internet-enabled partition at all,
`sra-tools` itself still needs to be reachable when it runs — talk to your
HPC support team about the right way to get outbound access for a batch job
on your system.

## Design notes

- **No third-party dependencies.** Downloading (`urllib`), extracting
  (`tarfile`), and everything else uses only the standard library, so the
  tool works on bare login-node Python installs.
- **Race-safe first install.** If many array tasks start at once and none
  of them find `sra-tools` installed yet, `which_or_install()` uses an
  `flock` lock around the download so only one task actually installs it
  while the rest wait and then reuse the same install.
- **Testable outside SLURM.** All the logic that matters — accession
  parsing, array-range math, template rendering — is plain Python with unit
  tests (`tests/`), independent of whether `sbatch` is even installed on the
  machine running the tests.
