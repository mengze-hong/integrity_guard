"""API integration tests for ZIP uploads and report generation."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import storage
from app.api import routes
from app.api import file_routes
from app.models import CheckResult
from tests.conftest import clear_route_state


@pytest.fixture()
def upload_client(tmp_path: Path, monkeypatch) -> TestClient:
    """Mount the real upload router with isolated upload and job storage."""
    uploads_dir = tmp_path / "uploads"
    jobs_dir = tmp_path / "jobs"
    uploads_dir.mkdir()
    jobs_dir.mkdir()

    monkeypatch.setattr(routes.settings, "upload_dir", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(routes.storage, "JOBS_DIR", jobs_dir)

    async def fast_reference_check(self, paper):
        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=True,
            score=100.0,
            summary="Reference check stubbed for upload API tests",
            metadata={"verified_entries": []},
        )

    monkeypatch.setattr(routes.ReferenceAuthenticityGate, "check", fast_reference_check)

    clear_route_state()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.include_router(file_routes.router, prefix="/api")

    with TestClient(app) as client:
        yield client

    clear_route_state()


def _zip_bytes(files: dict[str, str | bytes]) -> bytes:
    """Build ZIP bytes dynamically from archive paths to content."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for archive_path, content in files.items():
            zf.writestr(archive_path, content)
    return buffer.getvalue()


def _minimal_paper_zip(extra_files: dict[str, str | bytes] | None = None) -> bytes:
    files: dict[str, str | bytes] = {
        "paper/main.tex": (
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "A compact test paper cites prior work \\cite{smith2024}.\n"
            "\\bibliography{refs}\n"
            "\\end{document}\n"
        ),
        "paper/refs.bib": (
            "@article{smith2024,\n"
            "  title = {A Test Paper},\n"
            "  author = {Smith, Jane},\n"
            "  year = {2024},\n"
            "  journal = {Journal of Tests}\n"
            "}\n"
        ),
    }
    if extra_files:
        files.update(extra_files)
    return _zip_bytes(files)


def _upload(client: TestClient, content: bytes, filename: str = "paper.zip"):
    return client.post(
        "/api/upload",
        files={"file": (filename, content, "application/zip")},
    )


def _upload_report(client: TestClient, content: bytes, filename: str = "paper.zip") -> dict:
    response = _upload(client, content, filename)
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    report_response = client.get(f"/api/report/{job_id}")
    assert report_response.status_code == 200
    return report_response.json()


def _gate(report: dict, name: str) -> dict:
    return next(gate for gate in report["gate_results"] if gate["gate_name"] == name)


def _issue_text(gate: dict) -> str:
    return " ".join(issue["message"] for issue in gate["issues"])


def test_valid_zip_upload_completes_with_tex_and_bib_metadata(upload_client: TestClient):
    report = _upload_report(upload_client, _minimal_paper_zip())

    assert report["metadata"]["status"] == "completed"
    assert report["metadata"]["tex_count"] >= 1
    assert report["metadata"]["bib_count"] >= 1


def test_upload_rejects_non_zip_extension_synchronously(upload_client: TestClient):
    response = _upload(upload_client, _minimal_paper_zip(), filename="paper.txt")

    assert response.status_code == 400
    assert ".zip" in response.json()["detail"]


def test_corrupt_zip_with_valid_magic_uploads_then_fails(upload_client: TestClient):
    response = _upload(upload_client, b"PK\x03\x04not a real zip")
    assert response.status_code == 200

    job_id = response.json()["job_id"]
    report_response = upload_client.get(f"/api/report/{job_id}")

    assert report_response.status_code == 200
    report = report_response.json()
    assert report["metadata"]["status"] == "failed"
    assert report["metadata"]["error"]


def test_zip_slip_upload_fails_without_writing_outside_tmp(
    upload_client: TestClient,
    tmp_path: Path,
):
    report = _upload_report(
        upload_client,
        _zip_bytes({"../../escape.tex": "pwned"}),
    )

    assert report["metadata"]["status"] == "failed"
    assert "Unsafe path" in report["metadata"]["error"]
    assert not (tmp_path / "escape.tex").exists()


def test_dangerous_files_are_removed_and_not_listed(upload_client: TestClient):
    response = _upload(
        upload_client,
        _minimal_paper_zip({
            "paper/evil.exe": b"MZ binary",
            "paper/run.sh": "#!/bin/sh\nrm -rf /",
        }),
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    report_response = upload_client.get(f"/api/report/{job_id}")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["metadata"]["status"] == "completed"

    files_response = upload_client.get(f"/api/files/{job_id}")
    assert files_response.status_code == 200
    listed_paths = {item["path"] for item in files_response.json()["files"]}
    assert "evil.exe" not in listed_paths
    assert "run.sh" not in listed_paths

    project_dir = Path(report["project_dir"])
    assert not (project_dir / "evil.exe").exists()
    assert not (project_dir / "run.sh").exists()


def test_no_tex_zip_completes_with_structure_gate_failure(upload_client: TestClient):
    report = _upload_report(
        upload_client,
        _zip_bytes({
            "paper/refs.bib": (
                "@article{smith2024, title={A Test Paper}, "
                "author={Smith, Jane}, year={2024}}\n"
            )
        }),
    )

    structure = _gate(report, "structure_integrity")
    assert report["metadata"]["status"] == "completed"
    assert structure["passed"] is False
    assert ".tex" in _issue_text(structure)


def test_no_bib_zip_completes_with_structure_gate_failure(upload_client: TestClient):
    report = _upload_report(
        upload_client,
        _zip_bytes({
            "paper/main.tex": (
                "\\documentclass{article}\n"
                "\\begin{document}\n"
                "A compact test paper without bibliography files.\n"
                "\\end{document}\n"
            )
        }),
    )

    structure = _gate(report, "structure_integrity")
    assert report["metadata"]["status"] == "completed"
    assert structure["passed"] is False
    assert ".bib" in _issue_text(structure)
