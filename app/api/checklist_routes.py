"""Reproducibility checklist endpoint split out of ``app.api.routes``.

Only one endpoint lives here today (``POST /api/venue-checklist/{job_id}``),
but it is logically distinct from file CRUD, editor tools, and AI batch
fixes — it produces an ARR / NeurIPS submission checklist from the paper
content using the internal LLM gateway.

Pure structural slice from ``routes.py``: URL, behavior, permission model,
and rate-limit guard are unchanged. Permission/state/LLM helpers continue
to live in ``routes.py`` and are imported here.
"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.checklists import CHECKLISTS
from app.secrets_manager import redact

# Reuse the legacy module's permission, state, and LLM helpers so a single
# source of truth still owns access control and gateway plumbing.
from app.api.routes import (
    _require_job_access,
    _get_report,
    _job_dirs,
    _llm_chat_post,
    _llm_usage_guard,
)

router = APIRouter()


@router.post("/venue-checklist/{job_id}")
async def generate_venue_checklist(job_id: str, request: Request, response: Response):
    """AI-fill an official ARR / NeurIPS reproducibility checklist.

    The request body's ``venue`` selects the template (``arr`` by default;
    ``reproducibility`` is accepted as an alias for ``arr``). The endpoint
    requires write access to the job and goes through the per-IP / global
    LLM rate-limit guard before calling the gateway.

    The system prompt forbids inventing claims: items without supporting
    evidence in the paper excerpt are answered "no" with a concrete rewrite
    suggestion, never "yes". Errors from the gateway are redacted before
    being surfaced.
    """
    await _require_job_access(job_id, request, response, write=True)
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        body = await request.json()
    except Exception:
        body = {}
    venue = str(body.get("venue", "arr")).lower()
    if venue == "reproducibility":
        venue = "arr"
    template = CHECKLISTS.get(venue, CHECKLISTS["arr"])
    checklist = template["items"]

    # Pull the first .tex that declares \documentclass; that is the main
    # entry point. Bound to the first 10k chars so the LLM call stays cheap
    # and predictable for very long projects.
    main_text = ""
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            main_text = content[:10000]
            break

    if not main_text:
        return {"status": "error", "detail": "No main .tex found"}

    checklist_str = "\n".join(
        [f"- [{item['id']}] ({item['section']}) {item['text']}" for item in checklist]
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await _llm_chat_post(
                client,
                [
                    {"role": "system", "content": f"""You are an academic reproducibility assistant helping authors fill out the official {template['name']} for their paper.

For each checklist item, determine:
- "yes": The paper addresses this. Provide the exact section/paragraph evidence if visible.
- "no": The paper does NOT address this. Write a brief justification and a concrete rewrite/addition suggestion.
- "na": Not applicable. Explain why in one sentence.

IMPORTANT:
- Use the checklist IDs exactly as provided.
- The justification must be a complete sentence that can be directly pasted into the submission form.
- Write in English (this is for conference submission).
- If the paper is missing evidence, answer "no"; do not infer unstated compliance.
- Include an "evidence" field for every item. Use "Not found in provided excerpt" if no evidence is visible.
- For "no", include "missing_type": "missing_from_paper" or "insufficient_evidence".
- Include "rewrite_suggestion" for "no" items. Keep it actionable but do not invent claims or results.

Examples:
- {{"id":"C1","answer":"yes","evidence":"Section 1 states that code will be released in an anonymized repository.","justification":"We release our source code at the anonymized repository linked in Section 1, with a README describing how to reproduce all results.","missing_type":"","rewrite_suggestion":""}}
- {{"id":"E3","answer":"no","evidence":"Not found in provided excerpt","justification":"We report only single-run results; we will add mean and standard deviation over multiple seeds.","missing_type":"missing_from_paper","rewrite_suggestion":"Add a paragraph in the Experiments section reporting mean and standard deviation over multiple random seeds."}}
- {{"id":"T1","answer":"na","evidence":"The paper excerpt describes empirical experiments only.","justification":"Our work is empirical and contains no theoretical claims requiring proofs.","missing_type":"","rewrite_suggestion":""}}

Output as JSON array."""},
                    {"role": "user", "content": f"Checklist items:\n{checklist_str}\n\nPaper content:\n{main_text[:6000]}"},
                ],
                max_tokens=3000,
                temperature=0.2,
            )
            if resp.status_code == 200:
                data = resp.json()
                result_text = data["choices"][0]["message"]["content"].strip()
                json_match = result_text
                if "```" in json_match:
                    json_match = json_match.split("```")[1].replace("json", "").strip()
                try:
                    answers = json.loads(json_match)
                except json.JSONDecodeError:
                    answers = []

                # Merge LLM answers back into the canonical checklist so
                # missing items still appear with answer="unknown" rather
                # than dropping out of the response.
                result = []
                for item in checklist:
                    answer_data = next((a for a in answers if a.get("id") == item["id"]), None)
                    result.append({
                        **item,
                        "answer": answer_data.get("answer", "unknown") if answer_data else "unknown",
                        "justification": answer_data.get("justification", answer_data.get("reason", "")) if answer_data else "",
                        "evidence": answer_data.get("evidence", "") if answer_data else "",
                        "missing_type": answer_data.get("missing_type", "") if answer_data else "",
                        "rewrite_suggestion": answer_data.get("rewrite_suggestion", "") if answer_data else "",
                    })

                return {
                    "status": "ok",
                    "venue": venue,
                    "name": template["name"],
                    "source": template["source"],
                    "checklist": result,
                }
            else:
                return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}
