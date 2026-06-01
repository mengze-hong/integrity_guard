"""Tests for share-token redaction in /api/report.

Owners must keep getting the full payload; share-readonly viewers must
not see ownership identifiers, the share token itself, the on-disk
``project_dir``, or the dismiss audit trail.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.api import file_routes
from app.models import (
    CheckResult,
    DismissedIssue,
    FullReport,
    Issue,
    Severity,
)
from tests.conftest import clear_route_state


def _seed_report(job_id: str, share_token: str, owner_session: str) -> FullReport:
    issue = Issue(
        severity=Severity.WARNING,
        message="duplicate citation",
        location="main.tex",
    )
    gate = CheckResult(
        gate_name="citation_bib_consistency",
        gate_description="Citation/bib consistency",
        passed=False,
        score=70.0,
        summary="example",
        issues=[issue],
    )
    dismissed = DismissedIssue(
        gate_name="citation_bib_consistency",
        issue_index=0,
        original_message="duplicate citation",
        reason="this is intentional, see Section 3 (private student note)",
        severity=Severity.WARNING,
    )
    report = FullReport(
        job_id=job_id,
        filename="paper.tex",
        gate_results=[gate],
        dismissed_issues=[dismissed],
        overall_passed=False,
        overall_score=70.0,
        timestamp="2026-06-01T00:00:00Z",
        project_dir="/srv/secret/uploads/job-1/extracted",
        metadata={
            "owner_type": "session",
            "owner_id": owner_session,
            "session_id": owner_session,
            "share_token": share_token,
        },
    )
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"
    routes._job_owners[job_id] = {
        "owner_type": "session",
        "owner_id": owner_session,
        "session_id": owner_session,
        "share_token": share_token,
    }
    return report


@pytest.fixture()
def share_app():
    clear_route_state()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.include_router(file_routes.router, prefix="/api")
    yield app
    clear_route_state()


def test_owner_sees_full_report(share_app):
    job_id = "job-1"
    owner_session = "owner-sess-xyz"
    share_token = "secret-share-token-abc"
    _seed_report(job_id, share_token, owner_session)

    client = TestClient(share_app)
    client.cookies.set(routes.SESSION_COOKIE_NAME, owner_session)
    resp = client.get(f"/api/report/{job_id}")
    assert resp.status_code == 200
    body = resp.json()

    # Owners get the full payload — including their own metadata.
    assert body["metadata"]["owner_id"] == owner_session
    assert body["metadata"]["share_token"] == share_token
    assert body["project_dir"] == "/srv/secret/uploads/job-1/extracted"
    assert len(body["dismissed_issues"]) == 1


def test_share_viewer_sees_redacted_report(share_app):
    job_id = "job-1"
    owner_session = "owner-sess-xyz"
    share_token = "secret-share-token-abc"
    _seed_report(job_id, share_token, owner_session)

    client = TestClient(share_app)
    # Different (anonymous) caller, presenting only the share token.
    resp = client.get(
        f"/api/report/{job_id}",
        headers={"X-Share-Token": share_token},
    )
    assert resp.status_code == 200
    body = resp.json()

    # Owner identifiers and the token must not be echoed back.
    metadata = body.get("metadata") or {}
    assert "owner_id" not in metadata
    assert "owner_type" not in metadata
    assert "session_id" not in metadata
    assert "share_token" not in metadata
    # Server-internal extracted-project path is hidden.
    assert body["project_dir"] == ""
    # Dismiss list (student-authored reasons) is owner-only.
    assert body["dismissed_issues"] == []
    # But gate results / scores still come through so mentors can review.
    assert body["overall_score"] == 70.0
    assert body["gate_results"][0]["gate_name"] == "citation_bib_consistency"


def test_share_viewer_without_token_blocked(share_app):
    job_id = "job-1"
    owner_session = "owner-sess-xyz"
    share_token = "secret-share-token-abc"
    _seed_report(job_id, share_token, owner_session)

    client = TestClient(share_app)
    # No share token, no owner cookie, no auth — must be denied.
    resp = client.get(f"/api/report/{job_id}")
    assert resp.status_code == 403


def test_wrong_share_token_denied(share_app):
    job_id = "job-1"
    _seed_report(job_id, "secret-share-token-abc", "owner-sess-xyz")

    client = TestClient(share_app)
    resp = client.get(
        f"/api/report/{job_id}",
        headers={"X-Share-Token": "WRONG"},
    )
    assert resp.status_code == 403


def test_redact_helper_does_not_mutate_input():
    payload = {
        "project_dir": "/x",
        "dismissed_issues": [{"reason": "x"}],
        "metadata": {"owner_id": "u1", "share_token": "tok"},
    }
    snapshot_meta = dict(payload["metadata"])
    redacted = routes._share_readonly_report_payload(payload)
    # Source unchanged.
    assert payload["project_dir"] == "/x"
    assert payload["metadata"] == snapshot_meta
    assert payload["dismissed_issues"] == [{"reason": "x"}]
    # Returned copy redacted.
    assert redacted["project_dir"] == ""
    assert "owner_id" not in redacted["metadata"]
    assert "share_token" not in redacted["metadata"]
    assert redacted["dismissed_issues"] == []
