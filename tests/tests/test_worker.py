from pathlib import Path

import pytest

from sra_array_fetch import worker


def test_get_accession_basic(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("SRR100\nSRR101\nSRR102\n")
    assert worker.get_accession(ids, 1) == "SRR100"
    assert worker.get_accession(ids, 2) == "SRR101"
    assert worker.get_accession(ids, 3) == "SRR102"


def test_get_accession_strips_whitespace(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("  SRR100  \r\nSRR101\n")
    assert worker.get_accession(ids, 1) == "SRR100"


def test_get_accession_out_of_range_raises(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("SRR100\n")
    with pytest.raises(ValueError):
        worker.get_accession(ids, 5)


def test_get_accession_blank_line_raises(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("SRR100\n\nSRR102\n")
    with pytest.raises(ValueError):
        worker.get_accession(ids, 2)


def test_run_requires_task_id(tmp_path, monkeypatch):
    monkeypatch.delenv("SLURM_ARRAY_TASK_ID", raising=False)
    ids = tmp_path / "ids.txt"
    ids.write_text("SRR100\n")
    with pytest.raises(RuntimeError):
        worker.run(
            ids_file=ids,
            outdir=tmp_path / "out",
            sra_cache=tmp_path / "cache",
            tools_dir=tmp_path / "tools",
        )
