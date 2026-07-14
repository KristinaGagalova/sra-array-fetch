from pathlib import Path

import pytest

from sra_array_fetch import submit as submit_mod


def _write_ids(tmp_path: Path, n: int) -> Path:
    ids = tmp_path / "SRR_Acc_List.txt"
    ids.write_text("\n".join(f"SRR{1000+i}" for i in range(n)) + "\n")
    return ids


def test_count_accessions(tmp_path):
    ids = _write_ids(tmp_path, 5)
    assert submit_mod.count_accessions(ids) == 5


def test_count_accessions_ignores_blank_lines(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("SRR1\n\nSRR2\n\n\nSRR3\n")
    assert submit_mod.count_accessions(ids) == 3


def test_compute_array_range_defaults_to_full_list(tmp_path):
    ids = _write_ids(tmp_path, 279)
    array_range, total = submit_mod.compute_array_range(ids)
    assert array_range == "1-279"
    assert total == 279


def test_compute_array_range_custom_start_end(tmp_path):
    ids = _write_ids(tmp_path, 10)
    array_range, total = submit_mod.compute_array_range(ids, start=3, end=7)
    assert array_range == "3-7"
    assert total == 10


def test_compute_array_range_clamps_end(tmp_path, capsys):
    ids = _write_ids(tmp_path, 10)
    array_range, total = submit_mod.compute_array_range(ids, end=999)
    assert array_range == "1-10"
    captured = capsys.readouterr()
    assert "clamping" in captured.err


def test_compute_array_range_with_throttle(tmp_path):
    ids = _write_ids(tmp_path, 279)
    array_range, _ = submit_mod.compute_array_range(ids, throttle=20)
    assert array_range == "1-279%20"


def test_compute_array_range_empty_file_raises(tmp_path):
    ids = tmp_path / "empty.txt"
    ids.write_text("")
    with pytest.raises(ValueError):
        submit_mod.compute_array_range(ids)


def test_compute_array_range_invalid_bounds_raises(tmp_path):
    ids = _write_ids(tmp_path, 10)
    with pytest.raises(ValueError):
        submit_mod.compute_array_range(ids, start=8, end=3)


def test_render_script_substitutes_all_placeholders(tmp_path):
    script = submit_mod.render_script(
        job_name="sra_array",
        account="pawsey1142",
        array_range="1-279",
        cpus=8,
        mem="16G",
        walltime="12:00:00",
        log_dir=tmp_path / "logs",
        ids_file=tmp_path / "ids.txt",
        outdir=tmp_path / "out",
        sra_cache=tmp_path / "cache",
        tools_dir=tmp_path / "tools",
        max_size="100G",
        python_exe="python3",
    )
    assert "__" not in script  # no leftover placeholder markers
    assert "#SBATCH --account=pawsey1142" in script
    assert "#SBATCH --array=1-279" in script
    assert "run-task" in script


def test_submit_dry_run_writes_script(tmp_path):
    ids = _write_ids(tmp_path, 5)
    result = submit_mod.submit(
        ids_file=ids,
        outdir=tmp_path / "out",
        sra_cache=tmp_path / "cache",
        tools_dir=tmp_path / "tools",
        account="pawsey1142",
        dry_run=True,
    )
    script_path = Path(result)
    assert script_path.exists()
    assert "#SBATCH --array=1-5" in script_path.read_text()
