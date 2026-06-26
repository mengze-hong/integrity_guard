"""Tests for the headless ``check_folder`` pipeline."""

import asyncio
import json
from pathlib import Path

import pytest

from app.core.check import check_folder, default_gates
from app.models import FullReport

FIXTURES = Path(__file__).parent / "fixtures"


def test_check_folder_returns_full_report():
    report = asyncio.run(check_folder(FIXTURES))
    assert isinstance(report, FullReport)
    assert report.filename == "fixtures"
    assert report.job_id  # auto-generated
    assert len(report.gate_results) == 6
    gate_names = [r.gate_name for r in report.gate_results]
    assert gate_names == [
        "structure_integrity",
        "citation_bib_consistency",
        "reference_authenticity",
        "figure_table_crossref",
        "data_integrity",
        "writing_quality",
    ]
    assert 0.0 <= report.overall_score <= 100.0


def test_check_folder_metadata_populated():
    report = asyncio.run(check_folder(FIXTURES))
    md = report.metadata
    assert md["status"] == "completed"
    assert md["tex_count"] >= 1
    assert md["bib_count"] >= 1
    assert md["word_count"] > 0
    assert md["page_estimate"] >= 0


def test_check_folder_serialises_to_json():
    report = asyncio.run(check_folder(FIXTURES))
    payload = report.model_dump(mode="json")
    encoded = json.dumps(payload)
    assert "gate_results" in encoded
    assert "overall_score" in encoded


def test_check_folder_custom_filename_and_jobid():
    report = asyncio.run(
        check_folder(FIXTURES, filename="my_paper.zip", job_id="job-xyz")
    )
    assert report.filename == "my_paper.zip"
    assert report.job_id == "job-xyz"


def test_check_folder_subset_gates():
    gates = default_gates()[:2]
    report = asyncio.run(check_folder(FIXTURES, gates=gates))
    assert len(report.gate_results) == 2


def test_check_folder_missing_dir_raises():
    with pytest.raises(FileNotFoundError):
        asyncio.run(check_folder(FIXTURES / "no_such_dir"))


def test_check_folder_does_not_modify_folder(tmp_path):
    src = FIXTURES
    target = tmp_path / "paper"
    target.mkdir()
    for f in src.iterdir():
        if f.is_file():
            (target / f.name).write_bytes(f.read_bytes())
    before = sorted(p.name for p in target.iterdir())
    asyncio.run(check_folder(target))
    after = sorted(p.name for p in target.iterdir())
    assert before == after
