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
            "message": "没有可自动修复的问题",
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
