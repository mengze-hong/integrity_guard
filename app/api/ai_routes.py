"""AI-focused API routes.

This module starts the migration away from the legacy all-in-one
``routes.py`` file while preserving the existing ``/api`` URL surface.
Shared helpers are imported from the legacy module until the surrounding
job/session services are split out.
"""

import json

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.api import routes as legacy
from app.config import settings
from app.secrets_manager import redact
from app.services.ai_reports import (
    build_diagnosis_payload,
    fallback_diagnosis,
    parse_diagnosis_response,
)

router = APIRouter()


@router.post("/ai-diagnosis/{job_id}")
async def ai_diagnosis_report(job_id: str, request: Request, response: Response):
    """Generate an actionable AI diagnosis from report summaries."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    report = legacy._get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    payload = build_diagnosis_payload(report)
    provenance = {
        "source": "ai-diagnosis",
        "gates": [gate["gate_name"] for gate in payload["gates"]],
        "issue_count": len(payload["top_issues"]),
        "metadata_keys": sorted(payload["metadata"].keys()),
        "model": settings.llm_model,
    }

    system_prompt = (
        "You are a senior academic submission advisor. Generate a concise, actionable "
        "pre-submission diagnosis from the provided quality-check summary. Do not invent "
        "paper content, references, results, venues, or claims. Return strict JSON with "
        "these keys: summary, top_priorities, quick_wins, estimated_time, risk_notes, "
        "next_actions. top_priorities should be a list of objects with title, reason, "
        "action, and target. Keep the advice practical and conservative."
    )
    user_prompt = (
        "Quality-check summary JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=900,
                temperature=0.2,
            )
        if resp.status_code != 200:
            return {
                "status": "ok",
                "diagnosis": fallback_diagnosis(payload),
                "fallback": True,
                "detail": f"LLM returned {resp.status_code}",
                "provenance": provenance,
            }
        data = resp.json()
        content = data["choices"][0]["message"].get("content") or data["choices"][0]["message"].get("reasoning_content", "")
        diagnosis, used_fallback = parse_diagnosis_response(content, payload)
        return {
            "status": "ok",
            "diagnosis": diagnosis,
            "fallback": used_fallback,
            "provenance": provenance,
        }
    except Exception as e:
        return {
            "status": "ok",
            "diagnosis": fallback_diagnosis(payload),
            "fallback": True,
            "detail": redact(str(e))[:100],
            "provenance": provenance,
        }
