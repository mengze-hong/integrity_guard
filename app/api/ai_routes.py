"""AI-focused API routes.

This module starts the migration away from the legacy all-in-one
``routes.py`` file while preserving the existing ``/api`` URL surface.
Shared helpers are imported from the legacy module until the surrounding
job/session services are split out.
"""

import json
import re

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


def _project_dir_or_404(job_id: str):
    if job_id not in legacy._job_dirs:
        legacy._get_report(job_id)
    project_dir = legacy._job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_dir


def _main_tex_excerpt(project_dir, limit: int) -> str:
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            return content[:limit]
    return ""


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
                creds=legacy._llm_creds(request),
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


@router.post("/ai-fix/{job_id}")
async def ai_fix_suggestion(job_id: str, request: Request, response: Response):
    """Use LLM to suggest a fix for a specific issue."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    project_dir = _project_dir_or_404(job_id)

    body = await request.json()
    issue_message = body.get("message", "")
    file_path = body.get("file", "")
    line_num = body.get("line")
    context = body.get("context", "")
    gate_name = body.get("gate", "")

    if not issue_message:
        raise HTTPException(status_code=400, detail="Missing issue message")

    if legacy._is_reference_authenticity_issue(gate_name, issue_message):
        return legacy._not_fixable_reference_payload(issue_message, gate_name)

    if file_path and not context:
        target = legacy.safe_project_file(project_dir, file_path, allowed_suffixes=(".tex", ".bib"))
        if target.exists():
            lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
            if line_num and line_num > 0:
                start = max(0, line_num - 5)
                end = min(len(lines), line_num + 5)
                context = "\n".join(lines[start:end])
            else:
                context = "\n".join(lines[:20])

    lang = legacy._detect_lang(context, issue_message)
    if lang == "zh":
        sys_prompt = (
            "你是一个 LaTeX 学术论文修复助手。这篇论文是中文写的。"
            "请返回修复后的【完整】代码片段：保留所有未改动的行，仅修正问题处，"
            "使其能够整体替换原始片段。只输出代码本身，不要解释、不要省略任何行。"
            "【重要】绝不要编造任何文献信息（作者、标题、期刊/会议、年份、DOI、页码）；"
            "若无法确定真实值，保持原样或留 TODO 占位让作者填写，切勿生成虚构内容。"
        )
        user_prompt = f"问题: {issue_message}\n\n原始片段:\n```latex\n{context}\n```\n\n请返回修复后的完整片段:"
    else:
        sys_prompt = (
            "You are a LaTeX academic writing assistant. The paper is written in ENGLISH, "
            "so your fix MUST be in English — never insert Chinese text. "
            "Return the COMPLETE corrected version of the snippet: keep every unchanged line "
            "intact and only fix the issue, so your output can replace the original snippet "
            "verbatim. Output only the code, no explanation, do not omit any line. "
            "IMPORTANT: NEVER fabricate bibliographic data (authors, titles, venues, years, "
            "DOIs, page numbers); if a real value is unknown, leave it unchanged or insert a "
            "TODO placeholder for the author — never invent citation content."
        )
        user_prompt = (
            f"Issue: {issue_message}\n\nOriginal snippet:\n```latex\n{context}\n```\n\n"
            "Return the complete corrected snippet:"
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=500,
                temperature=0.3,
                creds=legacy._llm_creds(request),
            )
            if resp.status_code == 200:
                data = resp.json()
                suggestion = legacy._strip_code_fence(data["choices"][0]["message"]["content"])
                return {
                    "status": "ok",
                    "suggestion": suggestion,
                    "original": context,
                    "file": file_path,
                    "risk": "medium",
                    "requires_manual_review": True,
                    "provenance": legacy._ai_fix_provenance(gate_name, file_path, line_num, context),
                }
            return {"status": "error", "detail": f"LLM API returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-batch-fix/{job_id}")
async def ai_batch_fix(job_id: str, request: Request, response: Response):
    """Batch AI fix: generate auditable suggestions for fixable issues."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    project_dir = _project_dir_or_404(job_id)

    report = legacy._get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    candidates, summary, skipped = legacy._collect_batch_fix_candidates(report, project_dir)

    if not candidates:
        return {
            "status": "ok",
            "fixes": [],
            "summary": summary,
            "skipped": skipped,
            "message": "No auto-fixable issues",
        }

    fixes = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in candidates:
            context = item["context"]
            lang = legacy._detect_lang(context, item["message"])
            if lang == "zh":
                sys_prompt = (
                    "你是 LaTeX 学术论文修复助手。这篇论文是中文写的，请用中文给出修复后的"
                    "代码片段。只输出可直接粘贴的代码，不要解释。"
                    "【重要】绝不要编造任何文献信息（作者、标题、期刊/会议、年份、DOI、页码）；"
                    "无法确定时保持原样或留占位，切勿生成虚构引用。"
                )
                user_prompt = f"问题: {item['message']}\n建议: {item['suggestion']}\n\n代码:\n```latex\n{context}\n```\n\n修复后:"
            else:
                sys_prompt = (
                    "You are a LaTeX academic writing assistant. The paper is written in ENGLISH, "
                    "so your fix MUST be in English — never insert Chinese text. "
                    "Return only the corrected LaTeX snippet, no explanation. "
                    "IMPORTANT: NEVER fabricate bibliographic data (authors, titles, venues, "
                    "years, DOIs, pages); if unknown, leave unchanged or use a TODO placeholder."
                )
                user_prompt = (
                    f"Issue: {item['message']}\nHint: {item['suggestion']}\n\n"
                    f"Code:\n```latex\n{context}\n```\n\nFixed:"
                )
            try:
                resp = await legacy._llm_chat_post(
                    client,
                    [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=400,
                    temperature=0.2,
                    creds=legacy._llm_creds(request),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    fix_text = legacy._strip_code_fence(data["choices"][0]["message"]["content"])
                    gate_name = item["gate_name"]
                    summary["generated"] += 1
                    summary["by_gate"].setdefault(gate_name, {})
                    summary["by_gate"][gate_name]["generated"] = summary["by_gate"][gate_name].get("generated", 0) + 1
                    fixes.append({
                        "gate_name": item["gate_name"],
                        "issue_index": item["issue_index"],
                        "file": item["file"],
                        "line": item["line"],
                        "message": item["message"],
                        "original": context,
                        "fixed": fix_text,
                        "can_apply": bool(context.strip() and fix_text.strip()),
                        "risk": "medium",
                        "requires_manual_review": True,
                        "provenance": legacy._ai_fix_provenance(item["gate_name"], item["file"], item["line"], context),
                    })
                else:
                    summary["skipped"]["llm_error"] = summary["skipped"].get("llm_error", 0) + 1
                    skipped.append({
                        "gate_name": item["gate_name"],
                        "issue_index": item["issue_index"],
                        "reason": "llm_error",
                        "message": item["message"],
                        "file": item["file"],
                        "line": item["line"],
                    })
            except Exception:
                summary["skipped"]["llm_exception"] = summary["skipped"].get("llm_exception", 0) + 1
                skipped.append({
                    "gate_name": item["gate_name"],
                    "issue_index": item["issue_index"],
                    "reason": "llm_exception",
                    "message": item["message"],
                    "file": item["file"],
                    "line": item["line"],
                })

    return {
        "status": "ok",
        "fixes": fixes,
        "total_fixable": summary["total_fixable"],
        "summary": summary,
        "skipped": skipped,
    }


@router.post("/ai-review/{job_id}")
async def ai_reviewer_simulation(job_id: str, request: Request, response: Response):
    """Simulate a peer reviewer reading the paper and identify weaknesses."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    project_dir = _project_dir_or_404(job_id)

    main_text = _main_tex_excerpt(project_dir, 8000)
    if not main_text:
        return {"status": "error", "detail": "No main .tex found"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": """You are a strict top-tier conference reviewer (ACL / NeurIPS / ICML level).
This is a [SIMULATED REVIEW], not an official decision. Read the paper excerpt below and provide:
1. **Strengths** (2-3 points, concise)
2. **Weaknesses** (3-5 points, specific and actionable)
3. **Questions for Authors** (2-3 key questions)
4. **Overall Score**: Accept / Borderline / Reject
5. **Action Items** (3-5 concrete revisions the authors should prioritize next)

Reply in English, clearly formatted. Start each point with '- '. Do not invent experiments, results, or citations that are not in the paper; when evidence is insufficient, state explicitly "no evidence seen in the provided excerpt". Be strict but fair, like a real reviewer."""},
                    {"role": "user", "content": f"Please review this paper:\n\n{main_text}"},
                ],
                max_tokens=1000,
                temperature=0.7,
                creds=legacy._llm_creds(request),
            )
            if resp.status_code == 200:
                data = resp.json()
                review = data["choices"][0]["message"]["content"].strip()
                return {"status": "ok", "review": review}
            return {"status": "error", "detail": f"LLM API returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-polish/{job_id}")
async def ai_polish_text(job_id: str, request: Request, response: Response):
    """Polish a selected paragraph to be more academic and fluent."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    _project_dir_or_404(job_id)

    body = await request.json()
    text = body.get("text", "")
    mode = body.get("mode", "academic")

    if not text or len(text) < 10:
        raise HTTPException(status_code=400, detail="Please select the text to polish")

    mode_prompts = {
        "academic": "Rewrite this into more academic, fluent English while preserving the original meaning. Use phrasing common in scholarly papers.",
        "concise": "Tighten this text, remove redundancy, and make it more concise and forceful while keeping all key information.",
        "formal": "Rewrite this in a more formal academic style, avoiding colloquial expressions and using passive voice and formal vocabulary.",
    }
    prompt = mode_prompts.get(mode, mode_prompts["academic"])

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": f"You are an academic writing polishing expert. {prompt}\n\nOutput only the polished text — no explanation or annotation. Keep LaTeX commands unchanged."},
                    {"role": "user", "content": text},
                ],
                max_tokens=max(1024, len(text) * 2),
                temperature=0.4,
                creds=legacy._llm_creds(request),
            )
            if resp.status_code == 200:
                data = resp.json()
                polished = data["choices"][0]["message"]["content"].strip()
                return {"status": "ok", "original": text, "polished": polished, "mode": mode}
            return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-abstract/{job_id}")
async def ai_optimize_abstract(job_id: str, request: Request, response: Response):
    """Optimize the paper's abstract based on full content analysis."""
    await legacy._require_job_access(job_id, request, response, write=True)
    legacy._llm_usage_guard(request)
    project_dir = _project_dir_or_404(job_id)

    main_text = ""
    abstract = ""
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            main_text = content[:6000]
            abs_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", content, re.DOTALL)
            if abs_match:
                abstract = abs_match.group(1).strip()
            break

    if not abstract:
        return {"status": "error", "detail": "No abstract found"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": """You are an academic writing expert. Optimize this paper's Abstract so that it is:
1. More concise and forceful (target 150-250 words)
2. Clearly structured: problem → method → results → conclusion
3. Emphasizes the contributions and novelty
4. Uses active voice and strong verbs

Factual constraints:
- Do not overstate experimental results, contributions, numbers, or conclusions not supported by the body excerpt
- Do not add non-existent metrics, datasets, baselines, SOTA claims, or citations
- If a claim in the original abstract has no evidence in the body excerpt, soften the wording rather than strengthen it
- Preserve LaTeX commands and scientific meaning; do not change numbers or citations

Output format:
**Optimized Abstract:**
[optimized text]

**Revision notes:**
- [reason for each change, 2-3 points]"""},
                    {"role": "user", "content": f"Current Abstract:\n{abstract}\n\nPaper body excerpt:\n{main_text[:3000]}"},
                ],
                max_tokens=800,
                temperature=0.5,
                creds=legacy._llm_creds(request),
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data["choices"][0]["message"]["content"].strip()
                return {"status": "ok", "original_abstract": abstract, "suggestion": result}
            return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}
