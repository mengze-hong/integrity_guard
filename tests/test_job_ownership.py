"""Tests for job owner/session/share-token authorization."""

from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import storage
from app.api import routes
from app.models import FullReport


@pytest.fixture()
def ownership_app(tmp_path, monkeypatch):
    """Create an isolated app with temp uploads/jobs and a fast checker."""
    uploads_dir = tmp_path / "uploads"
    jobs_dir = tmp_path / "jobs"
    uploads_dir.mkdir()
    jobs_dir.mkdir()

    monkeypatch.setattr(routes.settings, "upload_dir", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(routes.storage, "JOBS_DIR", jobs_dir)

    routes._jobs.clear()
    routes._job_status.clear()
    routes._job_dirs.clear()
    routes._job_progress.clear()
    routes._job_owners.clear()
    routes._rate_limit.clear()

    async def fake_run_checks(job_id, zip_path, extract_dir, filename, owner_metadata):
        project_dir = extract_dir / "paper"
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")

        report = FullReport(
            job_id=job_id,
            filename=filename,
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_dir=str(project_dir),
            metadata={
                "word_count": 1,
                "page_estimate": 0.0,
                "bib_count": 0,
                "tex_count": 1,
                **owner_metadata,
            },
        )
        routes._jobs[job_id] = report
        routes._job_status[job_id] = "completed"
        routes._job_dirs[job_id] = project_dir
        routes._job_owners[job_id] = routes._extract_owner_metadata(report)
        storage.save_report(job_id, report)
        if zip_path.exists():
            zip_path.unlink()

    monkeypatch.setattr(routes, "_run_checks", fake_run_checks)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    yield app

    routes._jobs.clear()
    routes._job_status.clear()
    routes._job_dirs.clear()
    routes._job_progress.clear()
    routes._job_owners.clear()
    routes._rate_limit.clear()


def _zip_bytes(tmp_path: Path) -> bytes:
    zip_path = tmp_path / "paper.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("paper/main.tex", "\\documentclass{article}\n")
    return zip_path.read_bytes()


def _upload(client: TestClient, tmp_path: Path) -> dict:
    response = client.post(
        "/api/upload",
        files={"file": ("paper.zip", _zip_bytes(tmp_path), "application/zip")},
    )
    assert response.status_code == 200
    return response.json()


def test_anonymous_upload_sets_session_and_owner_can_read(ownership_app, tmp_path):
    client = TestClient(ownership_app)
    upload = _upload(client, tmp_path)

    assert "sl_session" in client.cookies
    response = client.get(f"/api/report/{upload['job_id']}")

    assert response.status_code == 200
    assert response.json()["job_id"] == upload["job_id"]


def test_different_anonymous_session_cannot_read_report(ownership_app, tmp_path):
    owner = TestClient(ownership_app)
    upload = _upload(owner, tmp_path)

    other_session = TestClient(ownership_app)
    response = other_session.get(f"/api/report/{upload['job_id']}")

    assert response.status_code == 403


def test_share_token_is_read_only(ownership_app, tmp_path):
    owner = TestClient(ownership_app)
    upload = _upload(owner, tmp_path)
    job_id = upload["job_id"]
    share = upload["share_token"]

    shared = TestClient(ownership_app)
    assert shared.get(f"/api/status/{job_id}?share={share}").status_code == 200
    assert shared.get(f"/api/report/{job_id}?share={share}").status_code == 200
    assert shared.get(f"/api/export/{job_id}?share={share}").status_code == 200
    assert shared.get(f"/api/files/{job_id}?share={share}").status_code == 200
    assert shared.get(f"/api/files/{job_id}/main.tex?share={share}").status_code == 200

    response = shared.put(f"/api/files/{job_id}/main.tex?share={share}", content="changed")
    assert response.status_code == 403


def test_history_only_lists_current_owner_jobs(ownership_app, tmp_path):
    first = TestClient(ownership_app)
    first_upload = _upload(first, tmp_path)

    second = TestClient(ownership_app)
    second_upload = _upload(second, tmp_path)

    first_history = first.get("/api/history")
    second_history = second.get("/api/history")

    assert first_history.status_code == 200
    assert second_history.status_code == 200
    assert [job["job_id"] for job in first_history.json()["jobs"]] == [first_upload["job_id"]]
    assert [job["job_id"] for job in second_history.json()["jobs"]] == [second_upload["job_id"]]
