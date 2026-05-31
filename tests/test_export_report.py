"""Tests for branded Markdown report export."""

import re
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.models import CheckResult, FullReport, Issue, Severity
from tests.conftest import clear_route_state


@pytest.fixture()
def export_app():
    clear_route_state()
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    yield app
    clear_route_state()


def _seed_report(job_id: str = "job-export", timestamp: str | None = None) -> FullReport:
    report = FullReport(
        job_id=job_id,
        filename="paper.zip",
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        overall_passed=False,
        overall_score=82.0,
        metadata={
            "owner_type": "session",
            "owner_id": "session-author",
            "session_id": "session-author",
            "share_token": "share-token",
        },
        gate_results=[
            CheckResult(
                gate_name="structure_integrity",
                gate_description="Structure",
                passed=False,
                score=82.0,
                summary="Structure issue found",
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        message="Missing bibliography file",
                        location="main.tex",
                    )
                ],
            )
        ],
    )
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"
    routes._job_owners[job_id] = routes._extract_owner_metadata(report)
    return report


def _assert_branded_export(text: str, job_id: str, report_type: str) -> None:
    assert "ScholarLint · 投稿通" in text
    assert "https://scholarlint.com" in text
    assert f"报告 ID | `{job_id}`" in text
    assert f"报告类型 | {report_type}" in text
    assert re.search(r"检查时间 \| \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z \|", text)
    assert re.search(r"导出时间 \| \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z \|", text)
    assert not re.search(r"(检查时间|导出时间) \| [^|\n]*\.\d+", text)
    assert "自动化检查不等于录用保证" in text
    assert "引文、数据与科学结论需人工核实" in text
    assert "关卡 1: 文件结构" in text
    assert "Missing bibliography file" in text
    assert "IntegrityGuard" not in text
    assert "IntegrityAssurance" not in text


def test_author_export_includes_branded_header_footer(export_app):
    timestamp = datetime.now(timezone.utc).isoformat()
    job_id = _seed_report(timestamp=timestamp).job_id
    client = TestClient(export_app)
    client.cookies.set("sl_session", "session-author")

    response = client.get(f"/api/export/{job_id}")

    assert response.status_code == 200
    _assert_branded_export(response.text, job_id, "作者工作区版")


def test_author_export_with_wrong_share_param_stays_author_type(export_app):
    job_id = _seed_report().job_id
    client = TestClient(export_app)
    client.cookies.set("sl_session", "session-author")

    response = client.get(f"/api/export/{job_id}?share=wrong-token")

    assert response.status_code == 200
    _assert_branded_export(response.text, job_id, "作者工作区版")
    assert "导师只读分享版" not in response.text


def test_share_export_is_labeled_read_only_share(export_app):
    job_id = _seed_report().job_id
    client = TestClient(export_app)

    response = client.get(f"/api/export/{job_id}?share=share-token")

    assert response.status_code == 200
    _assert_branded_export(response.text, job_id, "导师只读分享版")
