"""Tests for the production-mode tightening of legacy (no-owner) job access."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import storage
from app.api import routes
from app.config import settings
from app.models import FullReport
from tests.conftest import clear_route_state


def _seed_legacy_report(job_id: str = "legacy-job") -> FullReport:
    """A report whose metadata has no owner_type/owner_id (pre-ownership)."""
    return FullReport(
        job_id=job_id,
        filename="legacy.zip",
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={"word_count": 1},  # no owner_type / owner_id / share_token
    )


@pytest.fixture()
def legacy_app(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    jobs_dir = tmp_path / "jobs"
    uploads_dir.mkdir()
    jobs_dir.mkdir()
    monkeypatch.setattr(routes.settings, "upload_dir", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(routes.storage, "JOBS_DIR", jobs_dir)
    clear_route_state()

    job_id = "legacy-job"
    report = _seed_legacy_report(job_id)
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    yield TestClient(app), job_id

    clear_route_state()


def test_legacy_job_readable_in_local_env(legacy_app, monkeypatch):
    """In local mode (default), no-owner reports stay accessible (demo compat)."""
    monkeypatch.setattr(settings, "app_env", "local")
    client, job_id = legacy_app
    r = client.get(f"/api/report/{job_id}")
    assert r.status_code == 200


def test_legacy_job_blocked_in_production(legacy_app, monkeypatch):
    """In production, missing owner metadata must close the access loophole."""
    monkeypatch.setattr(settings, "app_env", "production")
    client, job_id = legacy_app
    r = client.get(f"/api/report/{job_id}")
    assert r.status_code == 403


def test_legacy_job_blocked_in_prod_short_alias(legacy_app, monkeypatch):
    """`prod` alias should behave the same as `production`."""
    monkeypatch.setattr(settings, "app_env", "prod")
    client, job_id = legacy_app
    r = client.get(f"/api/report/{job_id}")
    assert r.status_code == 403


def test_owned_job_unaffected_in_production(tmp_path, monkeypatch):
    """A job with proper owner metadata is unaffected — owner still passes."""
    uploads_dir = tmp_path / "uploads"
    jobs_dir = tmp_path / "jobs"
    uploads_dir.mkdir()
    jobs_dir.mkdir()
    monkeypatch.setattr(routes.settings, "upload_dir", uploads_dir)
    monkeypatch.setattr(storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(routes.storage, "JOBS_DIR", jobs_dir)
    monkeypatch.setattr(settings, "app_env", "production")
    clear_route_state()

    job_id = "owned-job"
    owner_session = "owner-A"
    report = FullReport(
        job_id=job_id,
        filename="paper.zip",
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={
            "owner_type": "session",
            "owner_id": owner_session,
            "session_id": owner_session,
            "share_token": "tok",
        },
    )
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"
    routes._job_owners[job_id] = routes._extract_owner_metadata(report)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    client = TestClient(app)
    client.cookies.set(routes.SESSION_COOKIE_NAME, owner_session)

    r = client.get(f"/api/report/{job_id}")
    assert r.status_code == 200
    clear_route_state()
