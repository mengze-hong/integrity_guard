"""Tests for per-job edit history: tracking, diff, and revert."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import storage
from app.api import routes
from app.api import file_routes
from app.models import FullReport
from app.services import edit_history
from tests.conftest import clear_route_state


@pytest.fixture()
def history_client(tmp_path, monkeypatch):
    """Mount the API router with an isolated job that owns a temp project dir."""
    uploads_dir = tmp_path / "uploads"
    jobs_dir = tmp_path / "jobs"
    uploads_dir.mkdir()
    jobs_dir.mkdir()
    monkeypatch.setattr(routes.settings, "upload_dir", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(routes.storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(edit_history, "JOBS_DIR", jobs_dir)

    clear_route_state()

    job_id = "hist-job"
    owner_session = "owner-session"
    share_token = "share-token"
    project_dir = uploads_dir / job_id / "paper"
    project_dir.mkdir(parents=True)
    (project_dir / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
        encoding="utf-8",
    )

    report = FullReport(
        job_id=job_id,
        filename="paper.zip",
        timestamp=datetime.now(timezone.utc).isoformat(),
        project_dir=str(project_dir),
        metadata={
            "owner_type": "session",
            "owner_id": owner_session,
            "session_id": owner_session,
            "share_token": share_token,
        },
    )
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"
    routes._job_dirs[job_id] = project_dir
    routes._job_owners[job_id] = routes._extract_owner_metadata(report)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.include_router(file_routes.router, prefix="/api")
    client = TestClient(app)
    client.cookies.set(routes.SESSION_COOKIE_NAME, owner_session)
    yield client, job_id, share_token

    clear_route_state()
    edit_history.delete_history(job_id)


def _save(client, job_id, path, content):
    return client.put(f"/api/files/{job_id}/{path}", content=content.encode("utf-8"))


def test_saving_files_records_history(history_client):
    client, job_id, _ = history_client
    assert _save(client, job_id, "main.tex", "version one\n").status_code == 200
    assert _save(client, job_id, "main.tex", "version one\ntwo\n").status_code == 200

    r = client.get(f"/api/history-edits/{job_id}")
    assert r.status_code == 200
    entries = r.json()["entries"]
    # Newest first; two saves recorded.
    assert len(entries) == 2
    assert entries[0]["file_path"] == "main.tex"
    assert entries[0]["new_lines"] >= entries[0]["old_lines"]


def test_no_history_entry_for_unchanged_save(history_client):
    client, job_id, _ = history_client
    _save(client, job_id, "main.tex", "same content\n")
    _save(client, job_id, "main.tex", "same content\n")  # no-op
    entries = client.get(f"/api/history-edits/{job_id}").json()["entries"]
    assert len(entries) == 1


def test_history_diff_returns_before_and_after(history_client):
    client, job_id, _ = history_client
    _save(client, job_id, "main.tex", "alpha\n")
    _save(client, job_id, "main.tex", "alpha\nbeta\n")
    entries = client.get(f"/api/history-edits/{job_id}").json()["entries"]
    latest = entries[0]
    detail = client.get(f"/api/history-edits/{job_id}/{latest['id']}").json()
    assert detail["old_content"] == "alpha\n"
    assert detail["new_content"] == "alpha\nbeta\n"
    assert detail["revertable"] is True


def test_revert_restores_previous_content(history_client):
    client, job_id, _ = history_client
    _save(client, job_id, "main.tex", "first\n")
    _save(client, job_id, "main.tex", "first\nsecond\n")
    entries = client.get(f"/api/history-edits/{job_id}").json()["entries"]
    # The entry whose change added "second" has old_content == "first\n".
    second_edit = entries[0]
    r = client.post(f"/api/history-edits/{job_id}/{second_edit['id']}/revert")
    assert r.status_code == 200
    assert r.json()["content"] == "first\n"

    # File on disk is restored, and the revert itself is recorded.
    read_back = client.get(f"/api/files/{job_id}/main.tex").json()["content"]
    assert read_back == "first\n"
    entries_after = client.get(f"/api/history-edits/{job_id}").json()["entries"]
    assert len(entries_after) == 3


def test_share_token_cannot_revert(history_client):
    client, job_id, share_token = history_client
    _save(client, job_id, "main.tex", "x\n")
    _save(client, job_id, "main.tex", "x\ny\n")
    entry_id = client.get(f"/api/history-edits/{job_id}").json()["entries"][0]["id"]

    # A share-token reader (no owner cookie) may read history but not revert.
    reader = TestClient(client.app)
    list_resp = reader.get(f"/api/history-edits/{job_id}?share={share_token}")
    assert list_resp.status_code == 200
    revert_resp = reader.post(f"/api/history-edits/{job_id}/{entry_id}/revert?share={share_token}")
    assert revert_resp.status_code == 403
