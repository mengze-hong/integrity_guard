"""API-level tests for the dedicated AI router."""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import ai_routes, routes
from app.models import CheckResult, FullReport, Issue, Severity
from tests.conftest import clear_route_state


class MockLLMResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture()
def ai_app(tmp_path: Path):
    clear_route_state()

    job_id = "ai-route-job"
    owner_session = "owner-session"
    share_token = "share-token"
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
        metadata={
            "owner_type": "session",
            "owner_id": owner_session,
            "session_id": owner_session,
            "share_token": share_token,
        },
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
    routes._job_owners[job_id] = routes._extract_owner_metadata(report)

    app = FastAPI()
    app.include_router(ai_routes.router, prefix="/api")
    client = TestClient(app)
    client.cookies.set(routes.SESSION_COOKIE_NAME, owner_session)
    yield client, job_id

    clear_route_state()


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


def test_ai_diagnosis_rejects_share_token_write_access_before_llm(ai_app, monkeypatch):
    client, job_id = ai_app
    share_token = routes._jobs[job_id].metadata["share_token"]

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("share-token write access must be rejected before LLM calls")

    monkeypatch.setattr(routes, "_llm_chat_post", fail_if_called)
    client.cookies.clear()

    response = client.post(f"/api/ai-diagnosis/{job_id}?share={share_token}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.parametrize("wrap_in_fence", [True, False])
def test_ai_diagnosis_returns_model_json(ai_app, monkeypatch, wrap_in_fence):
    client, job_id = ai_app
    diagnosis = {
        "summary": "Resolve citation authenticity before submission.",
        "top_priorities": [
            {
                "title": "Verify fake citation",
                "reason": "The reference authenticity gate reported a blocking issue.",
                "action": "Replace it with a verified source or remove the claim.",
                "target": "main.tex:3",
            }
        ],
        "quick_wins": ["Open main.tex and inspect the fake citation."],
        "estimated_time": "15 minutes",
        "risk_notes": ["Do not invent bibliographic details."],
        "next_actions": ["Rerun the reference authenticity check."],
    }
    content = json.dumps(diagnosis)
    if wrap_in_fence:
        content = f"```json\n{content}\n```"

    async def fake_llm_chat_post(client, messages, **kwargs):
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert kwargs["max_tokens"] == 900
        user_prompt = messages[1]["content"]
        project_dir = routes._job_dirs[job_id]
        assert "reference_authenticity" in user_prompt
        assert "DOI 无法解析" in user_prompt
        assert "fake" in user_prompt
        assert "main.tex" in user_prompt
        assert '"line": 3' in user_prompt
        assert "project_dir" not in user_prompt
        assert str(project_dir) not in user_prompt
        assert str(project_dir.parent) not in user_prompt
        return MockLLMResponse(
            200,
            {"choices": [{"message": {"content": content}}]},
        )

    monkeypatch.setattr(routes, "_llm_chat_post", fake_llm_chat_post)

    response = client.post(f"/api/ai-diagnosis/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["fallback"] is False
    assert payload["diagnosis"]["summary"] == diagnosis["summary"]
    assert payload["provenance"]["source"] == "ai-diagnosis"
    assert payload["provenance"]["model"]
    assert payload["provenance"]["gates"] == ["reference_authenticity"]


def test_ai_diagnosis_uses_fallback_for_non_200_llm(ai_app, monkeypatch):
    client, job_id = ai_app

    async def fake_llm_chat_post(client, messages, **kwargs):
        return MockLLMResponse(503)

    monkeypatch.setattr(routes, "_llm_chat_post", fake_llm_chat_post)

    response = client.post(f"/api/ai-diagnosis/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["fallback"] is True
    assert payload["detail"] == "LLM returned 503"
    assert payload["diagnosis"]["summary"].startswith("Current score is")
    assert payload["diagnosis"]["top_priorities"][0]["title"] == "[fake] DOI 无法解析，标题搜索未找到匹配"
    assert payload["provenance"]["source"] == "ai-diagnosis"


def test_ai_diagnosis_missing_job_returns_404(ai_app, monkeypatch):
    client, _job_id = ai_app

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("missing jobs must not call the LLM")

    monkeypatch.setattr(routes, "_llm_chat_post", fail_if_called)

    response = client.post("/api/ai-diagnosis/missing-job")

    assert response.status_code == 404
