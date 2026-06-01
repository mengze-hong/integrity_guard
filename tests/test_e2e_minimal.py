"""Minimal API-level E2E coverage for upload, editing, and recheck."""

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
def e2e_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Mount the real API router with isolated upload and job storage."""
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
            summary="Reference check stubbed for minimal E2E",
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


def _minimal_zip(main_tex: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("paper/main.tex", main_tex)
        zf.writestr(
            "paper/refs.bib",
            (
                "@article{smith2024,\n"
                "  title = {A Test Paper},\n"
                "  author = {Smith, Jane},\n"
                "  year = {2024},\n"
                "  journal = {Journal of Tests}\n"
                "}\n"
            ),
        )
    return buffer.getvalue()


def _gate(report: dict, name: str) -> dict:
    return next(gate for gate in report["gate_results"] if gate["gate_name"] == name)


def _issue_text(gate: dict) -> str:
    return " ".join(issue["message"] for issue in gate["issues"])


def test_minimal_upload_edit_recheck_flow_updates_report(e2e_client: TestClient):
    original_main = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "A compact test paper cites prior work \\cite{smith2024}.\n"
        "\\begin{figure}\n"
        "\\caption{Overview of the proposed workflow.}\n"
        "\\end{figure}\n"
        "\\bibliography{refs}\n"
        "\\end{document}\n"
    )
    fixed_main = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "A compact test paper cites prior work \\cite{smith2024}. "
        "Figure~\\ref{fig:overview} summarizes the workflow.\n"
        "\\begin{figure}\n"
        "\\caption{Overview of the proposed workflow.}\n"
        "\\label{fig:overview}\n"
        "\\end{figure}\n"
        "\\bibliography{refs}\n"
        "\\end{document}\n"
    )

    upload_response = e2e_client.post(
        "/api/upload",
        files={"file": ("paper.zip", _minimal_zip(original_main), "application/zip")},
    )
    assert upload_response.status_code == 200
    job_id = upload_response.json()["job_id"]

    report_response = e2e_client.get(f"/api/report/{job_id}")
    assert report_response.status_code == 200
    initial_report = report_response.json()
    initial_figure_gate = _gate(initial_report, "figure_table_crossref")
    assert initial_report["metadata"]["status"] == "completed"
    assert initial_figure_gate["passed"] is False
    assert "\\label" in _issue_text(initial_figure_gate)

    files_response = e2e_client.get(f"/api/files/{job_id}")
    assert files_response.status_code == 200
    assert {item["path"] for item in files_response.json()["files"]} == {"main.tex", "refs.bib"}

    file_response = e2e_client.get(f"/api/files/{job_id}/main.tex")
    assert file_response.status_code == 200
    assert file_response.json()["content"] == original_main

    save_response = e2e_client.put(f"/api/files/{job_id}/main.tex", content=fixed_main)
    assert save_response.status_code == 200
    assert save_response.json()["status"] == "saved"

    saved_file_response = e2e_client.get(f"/api/files/{job_id}/main.tex")
    assert saved_file_response.status_code == 200
    assert saved_file_response.json()["content"] == fixed_main

    recheck_response = e2e_client.post(f"/api/recheck/{job_id}")
    assert recheck_response.status_code == 200
    assert recheck_response.json()["status"] == "processing"

    final_report_response = e2e_client.get(f"/api/report/{job_id}")
    assert final_report_response.status_code == 200
    final_report = final_report_response.json()
    final_figure_gate = _gate(final_report, "figure_table_crossref")

    assert final_report["metadata"]["status"] == "completed"
    assert final_figure_gate["passed"] is True
    assert final_figure_gate["score"] > initial_figure_gate["score"]
    assert final_figure_gate["issues"] == []
