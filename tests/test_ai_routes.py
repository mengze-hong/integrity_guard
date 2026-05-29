"""API-level tests for the dedicated AI router."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ai_routes, routes
from app.models import CheckResult, FullReport, Issue, Severity


@pytest.fixture()
def ai_app(tmp_path: Path):
    routes._jobs.clear()
    routes._job_status.clear()
    routes._job_dirs.clear()
    routes._job_owners.clear()
    routes._llm_calls_by_ip.clear()
    routes._llm_calls_global.clear()

    job_id = "ai-route-job"
    project_dir = tmp_path / "paper"
    project_dir.mkdir()
    (project_dir / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "A fake citation \\cite{fake}.\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    report = FullReport(
        job_id=job_id,
        filename="paper.zip",
        project_dir=str(project_dir),
        gate_results=[
            CheckResult(
                gate_name="reference_authenticity",
                gate_description="Reference authenticity",
                passed=False,
                score=0,
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        message="[fake] DOI 无法解析，标题搜索未找到匹配",
                        file="main.tex",
                        line=3,
                    )
                ],
            )
        ],
    )
    routes._jobs[job_id] = report
    routes._job_status[job_id] = "completed"
    routes._job_dirs[job_id] = project_dir

    app = FastAPI()
    app.include_router(ai_routes.router, prefix="/api")
    yield TestClient(app), job_id

    routes._jobs.clear()
    routes._job_status.clear()
    routes._job_dirs.clear()
    routes._job_owners.clear()
    routes._llm_calls_by_ip.clear()
    routes._llm_calls_global.clear()


def test_ai_fix_reference_guardrail_never_calls_llm(ai_app, monkeypatch):
    client, job_id = ai_app

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("reference authenticity fixes must not call the LLM")

    monkeypatch.setattr(routes, "_llm_chat_post", fail_if_called)

    response = client.post(
        f"/api/ai-fix/{job_id}",
        json={
            "gate": "reference_authenticity",
            "message": "[fake] DOI 无法解析，标题搜索未找到匹配",
            "file": "main.tex",
            "line": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_fixable"
    assert payload["candidate_search_available"] is True
    assert "suggestion" not in payload


def test_ai_batch_fix_reference_issue_returns_dry_run_without_llm(ai_app, monkeypatch):
    client, job_id = ai_app

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("reference authenticity batch fixes must not call the LLM")

    monkeypatch.setattr(routes, "_llm_chat_post", fail_if_called)

    response = client.post(f"/api/ai-batch-fix/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["fixes"] == []
    assert payload["summary"]["total_error_issues"] == 1
    assert payload["summary"]["total_fixable"] == 0
    assert payload["summary"]["skipped"]["reference_authenticity"] == 1
    assert payload["skipped"][0]["reason"] == "reference_authenticity"
