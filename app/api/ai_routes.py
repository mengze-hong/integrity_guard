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
                    {"role": "system", "content": """你是一位严格的顶会审稿人（ACL/NeurIPS/ICML level）。
这是【模拟审稿意见】，不是正式审稿结论。请阅读以下论文片段，给出：
1. **Strengths** (2-3 点，简洁)
2. **Weaknesses** (3-5 点，具体且可操作)
3. **Questions for Authors** (2-3 个关键问题)
4. **Overall Score**: Accept / Borderline / Reject
5. **Action Items** (3-5 条作者下一步应该优先完成的具体修改)

用中文回复，格式清晰。每点用 - 开头。不要编造论文中没有的实验、结果或引用；证据不足时明确写“论文片段中未看到证据”。注意：你应该像真正的审稿人一样严格但公正。"""},
                    {"role": "user", "content": f"请审阅这篇论文:\n\n{main_text}"},
                ],
                max_tokens=1000,
                temperature=0.7,
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
        raise HTTPException(status_code=400, detail="请选择要润色的文本")

    mode_prompts = {
        "academic": "改写为更加学术化、流畅的英文表达，保持原意不变。使用学术论文常见的表达方式。",
        "concise": "精简这段文字，去除冗余表达，使其更加简洁有力，同时保留所有关键信息。",
        "formal": "改写为更正式的学术写作风格，避免口语化表达，使用被动语态和正式词汇。",
    }
    prompt = mode_prompts.get(mode, mode_prompts["academic"])

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": f"你是一位学术论文润色专家。{prompt}\n\n只输出润色后的文本，不要任何解释或标注。保持 LaTeX 命令不变。"},
                    {"role": "user", "content": text},
                ],
                max_tokens=max(1024, len(text) * 2),
                temperature=0.4,
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
        return {"status": "error", "detail": "未找到 abstract"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await legacy._llm_chat_post(
                client,
                [
                    {"role": "system", "content": """你是一位学术写作专家。请优化这篇论文的 Abstract，使其：
1. 更加简洁有力（控制在 150-250 词）
2. 结构清晰：问题→方法→结果→结论
3. 突出贡献和创新点
4. 使用主动语态和强动词

关键事实约束：
- 不得夸大论文正文片段中没有支持的实验结果、贡献、数字或结论
- 不得新增不存在的指标、数据集、baseline、SOTA claim 或引用
- 如果原 abstract 的 claim 在正文片段中看不到证据，请降低措辞强度而不是增强
- 保留 LaTeX 命令和科学含义，不要改变数字与引用

输出格式：
**优化后的 Abstract:**
[优化后的文本]

**修改说明:**
- [每处修改的原因，2-3条]"""},
                    {"role": "user", "content": f"当前 Abstract:\n{abstract}\n\n论文正文片段:\n{main_text[:3000]}"},
                ],
                max_tokens=800,
                temperature=0.5,
            )
            if resp.status_code == 200:
                data = resp.json()
                result = data["choices"][0]["message"]["content"].strip()
                return {"status": "ok", "original_abstract": abstract, "suggestion": result}
            return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}
