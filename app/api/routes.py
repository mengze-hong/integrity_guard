"""API routes for integrity checks + file editor + human-in-the-loop."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import settings, LLM_RATE_PER_IP, LLM_RATE_WINDOW, LLM_GLOBAL_HOURLY_CAP
from app.secrets_manager import redact
from app.models import FullReport, DismissedIssue, Severity
from app.parsers.zip_parser import extract_zip, identify_project_structure
from app.parsers.tex_parser import parse_all_tex_files
from app.parsers.bib_parser import parse_all_bib_files
from app.checks.gate_structure import StructureGate
from app.checks.gate_references import ReferenceAuthenticityGate
from app.checks.gate_citations import CitationConsistencyGate
from app.checks.gate_figures import FigureTableGate
from app.checks.gate_data import DataIntegrityGate
from app.checks.gate_writing import WritingQualityGate
from app import storage
from app.logging_config import logger

router = APIRouter()

# In-memory caches (authoritative data is on disk via storage module)
_jobs: dict[str, FullReport] = {}
_job_status: dict[str, str] = {}
_job_dirs: dict[str, Path] = {}  # job_id → extracted project directory
_job_progress: dict[str, list[str]] = {}  # job_id → list of completed gate names


def _get_report(job_id: str) -> FullReport | None:
    """Get report from memory cache, falling back to disk."""
    if job_id in _jobs:
        return _jobs[job_id]
    # Try loading from disk
    report = storage.load_report(job_id)
    if report:
        _jobs[job_id] = report
        _job_status[job_id] = "completed"
        # Recover project_dir
        if report.project_dir:
            proj = Path(report.project_dir)
            if proj.exists():
                _job_dirs[job_id] = proj
        return report
    return None


def _persist(job_id: str):
    """Save current in-memory report to disk."""
    report = _jobs.get(job_id)
    if report:
        storage.save_report(job_id, report)


# ─── Rate Limiting ────────────────────────────────────────────
import time
_rate_limit: dict[str, list[float]] = {}  # ip → [timestamps]
RATE_LIMIT_MAX = 10  # max uploads per window
RATE_LIMIT_WINDOW = 3600  # 1 hour


def _check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate limited."""
    now = time.time()
    if ip not in _rate_limit:
        _rate_limit[ip] = []
    # Clean old entries
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limit[ip].append(now)
    return True


# ─── LLM usage caps (anti-abuse / cost control) ───────────────
from collections import defaultdict
_llm_calls_by_ip: dict[str, list[float]] = defaultdict(list)
_llm_calls_global: list[float] = []


def _llm_usage_guard(request: Request):
    """Enforce per-IP rate limit + global hourly cap on LLM-backed endpoints.

    Raises HTTP 429 when a limit is exceeded. Protects the internal LLM from
    abuse (important when the app is exposed via a public tunnel).
    """
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    global _llm_calls_global
    _llm_calls_global[:] = [t for t in _llm_calls_global if now - t < 3600]
    _llm_calls_by_ip[ip] = [t for t in _llm_calls_by_ip[ip] if now - t < LLM_RATE_WINDOW]

    if len(_llm_calls_global) >= LLM_GLOBAL_HOURLY_CAP:
        raise HTTPException(status_code=429, detail="AI 服务已达全局用量上限，请稍后再试")
    if len(_llm_calls_by_ip[ip]) >= LLM_RATE_PER_IP:
        raise HTTPException(status_code=429, detail="AI 调用过于频繁，请稍后再试")

    _llm_calls_by_ip[ip].append(now)
    _llm_calls_global.append(now)
    # Bound memory: drop empty/stale IP buckets occasionally
    if len(_llm_calls_by_ip) > 5000:
        for k in [k for k, v in _llm_calls_by_ip.items() if not v]:
            del _llm_calls_by_ip[k]


# ─── Shared LLM call helper ───────────────────────────────────
# Reasoning models (e.g. gpt-5.5) reject a non-default `temperature`; this
# helper transparently retries without it so all AI features keep working
# regardless of which model `LLM_MODEL` points to.

async def _llm_chat_post(client, messages, max_tokens, temperature=None):
    """POST a chat completion to the LiteLLM proxy with graceful fallback."""
    url = f"{settings.llm_base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    payload = {"model": settings.llm_model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload["temperature"] = temperature

    resp = await client.post(url, headers=headers, json=payload)
    if (
        resp.status_code == 400
        and "temperature" in payload
        and "temperature" in resp.text.lower()
    ):
        payload.pop("temperature", None)
        resp = await client.post(url, headers=headers, json=payload)
    return resp


def _strip_code_fence(text: str) -> str:
    """Remove a wrapping markdown code fence (```lang ... ```), if present.

    LLMs often wrap code in fences; inserting those into a .tex file breaks it.
    """
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


_REF_ISSUE_KEYWORDS = (
    "DOI 无法解析", "无法解析", "fabricat", "伪造", "retract", "撤稿",
    "无法验证", "未找到该文献", "不存在的文献", "虚构",
    "缺少 DOI", "无可信来源", "标题搜索未找到", "source not found",
    "Unverified reference", "official URL/DOI", "DOI/source not found",
)


def _is_reference_authenticity_issue(gate_name: str = "", message: str = "") -> bool:
    """True if an issue concerns citation/reference authenticity.

    Such issues must NOT be auto-"fixed" by the LLM, because fabricating a
    replacement reference is itself an integrity violation.
    """
    if gate_name == "reference_authenticity":
        return True
    msg = message or ""
    return any(k in msg for k in _REF_ISSUE_KEYWORDS)


def _detect_lang(*texts: str) -> str:
    """Roughly detect whether the given text is mainly Chinese or English.

    Returns "zh" if CJK characters make up a meaningful share, else "en".
    Used so AI fixes inserted into the paper match the paper's language.
    """
    sample = " ".join(t for t in texts if t)
    if not sample:
        return "en"
    cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    # Even a modest amount of CJK means the paper is Chinese-language.
    if cjk >= 8 or (cjk > 0 and cjk * 4 >= latin):
        return "zh"
    return "en"


# ─── Upload & Check ───────────────────────────────────────────

@router.post("/upload")
async def upload_paper(request: Request, background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a zip file and start integrity checks."""
    from app.dependencies import get_current_user_optional
    from app.credits import deduct_credits, InsufficientCredits
    from app.database import SessionLocal

    # Check auth + credits
    user = await get_current_user_optional(request)
    if user:
        db = SessionLocal()
        try:
            deduct_credits(db, user.id, settings.credits_upload, "论文质检")
        except InsufficientCredits:
            raise HTTPException(status_code=402, detail="积分不足，请充值")
        finally:
            db.close()
    else:
        # Anonymous user: rate limit by IP
        client_ip = request.client.host if request.client else "unknown"
        if not _check_rate_limit(client_ip):
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试（每小时最多 10 次）")

    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 文件")

    # Security: check Content-Length header before reading
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大（最大 100MB）")

    content = await file.read()

    # Security: file size check (max 100MB)
    if len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（最大 100MB）")

    job_id = uuid.uuid4().hex[:12]  # 12 hex chars = 48 bits entropy
    upload_path = settings.upload_dir / f"{job_id}.zip"
    extract_dir = settings.upload_dir / job_id

    with open(upload_path, "wb") as f:
        f.write(content)

    _job_status[job_id] = "processing"
    background_tasks.add_task(_run_checks, job_id, upload_path, extract_dir, file.filename)

    return {"job_id": job_id, "status": "processing"}


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    status = _job_status.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": status,
        "progress": _job_progress.get(job_id, []),
    }


@router.get("/report/{job_id}")
async def get_report(job_id: str):
    report = _get_report(job_id)
    if not report:
        status = _job_status.get(job_id, "not_found")
        if status == "processing":
            raise HTTPException(status_code=202, detail="Still processing")
        raise HTTPException(status_code=404, detail="Report not found")
    return report.model_dump()


# ─── File CRUD (for editor) ───────────────────────────────────

@router.get("/files/{job_id}")
async def list_files(job_id: str):
    """List all editable files (.tex, .bib) in the project."""
    # Ensure job_dirs is populated (may need disk recovery)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    files = []
    for f in sorted(project_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".tex", ".bib"):
            rel = f.relative_to(project_dir)
            files.append({
                "path": str(rel).replace("\\", "/"),
                "name": f.name,
                "type": "tex" if f.suffix == ".tex" else "bib",
                "size": f.stat().st_size,
            })
    return {"files": files}


@router.get("/files/{job_id}/{file_path:path}")
async def read_file(job_id: str, file_path: str):
    """Read a file's content."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    target = project_dir / file_path
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Security: ensure path is within project
    try:
        target.resolve().relative_to(project_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {"path": file_path, "content": content}


@router.put("/files/{job_id}/{file_path:path}")
async def save_file(job_id: str, file_path: str, request: Request):
    """Save file content (auto-save from editor)."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    # Security: only allow editing known plain-text source files (blocks
    # writing binaries/executables while preserving editor functionality)
    EDITABLE_EXTENSIONS = (".tex", ".bib", ".cls", ".sty", ".bst", ".txt", ".md")
    if not any(file_path.lower().endswith(ext) for ext in EDITABLE_EXTENSIONS):
        raise HTTPException(status_code=403, detail="只能编辑文本源文件（.tex/.bib/.cls/.sty 等）")

    target = project_dir / file_path
    try:
        target.resolve().relative_to(project_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    body = await request.body()
    content = body.decode("utf-8")
    target.write_text(content, encoding="utf-8")

    return {"status": "saved", "path": file_path, "size": len(content)}


# ─── Recheck (re-run checks on modified files) ────────────────

@router.post("/recheck/{job_id}")
async def recheck(request: Request, job_id: str, background_tasks: BackgroundTasks):
    """Re-run all checks on the (possibly modified) project files."""
    from app.dependencies import get_current_user_optional
    from app.credits import deduct_credits, InsufficientCredits
    from app.database import SessionLocal

    # Deduct credits if logged in
    user = await get_current_user_optional(request)
    if user:
        db = SessionLocal()
        try:
            deduct_credits(db, user.id, settings.credits_recheck, "重新质检")
        except InsufficientCredits:
            raise HTTPException(status_code=402, detail="积分不足，请充值")
        finally:
            db.close()

    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    report = _jobs.get(job_id)
    filename = report.filename if report else "unknown.zip"

    # Keep dismissed issues from previous run
    old_dismissed = report.dismissed_issues if report else []

    _job_status[job_id] = "processing"
    background_tasks.add_task(_run_checks_from_dir, job_id, project_dir, filename, old_dismissed)

    return {"job_id": job_id, "status": "processing"}


# ─── Human-in-the-Loop: Dismiss ──────────────────────────────

@router.post("/dismiss/{job_id}")
async def dismiss_issue(job_id: str, request: Request):
    """Student dismisses an issue with a reason."""
    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    body = await request.json()
    gate_name = body.get("gate_name")
    issue_index = body.get("issue_index")
    reason = body.get("reason", "").strip()

    if not reason:
        raise HTTPException(status_code=400, detail="必须填写忽略理由")
    if not gate_name or issue_index is None:
        raise HTTPException(status_code=400, detail="Missing gate_name or issue_index")

    # Find the issue
    gate = next((g for g in report.gate_results if g.gate_name == gate_name), None)
    if not gate or issue_index >= len(gate.issues):
        raise HTTPException(status_code=404, detail="Issue not found")

    issue = gate.issues[issue_index]

    dismissed = DismissedIssue(
        gate_name=gate_name,
        issue_index=issue_index,
        reason=reason,
        original_message=issue.message,
        severity=issue.severity,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    report.dismissed_issues.append(dismissed)
    _persist(job_id)

    return {"status": "dismissed", "total_dismissed": len(report.dismissed_issues)}


# ─── Export Report (for supervisor) ──────────────────────────

@router.get("/export/{job_id}")
async def export_report(job_id: str):
    """Export a human-readable report for supervisor review."""
    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    lines = []
    lines.append("# IntegrityGuard — 论文完整性检查报告")
    lines.append("")
    lines.append(f"| 项目 | 详情 |")
    lines.append(f"|------|------|")
    lines.append(f"| 📁 文件 | {report.filename} |")
    lines.append(f"| 📅 日期 | {report.timestamp[:10]} {report.timestamp[11:16]} UTC |")
    lines.append(f"| 📊 得分 | **{report.overall_score:.0f}/100** |")

    dismissed_count = len(report.dismissed_issues)
    if report.overall_passed and dismissed_count == 0:
        lines.append(f"| 🏆 总评 | 全部通过 — 可安全提交 |")
    elif report.overall_passed and dismissed_count > 0:
        lines.append(f"| ⚠️ 总评 | 通过（{dismissed_count} 项被学生标记为非问题，需导师确认）|")
    else:
        error_total = sum(
            sum(1 for iss in g.issues if iss.severity == "error")
            for g in report.gate_results
        )
        lines.append(f"| ❌ 总评 | 未通过（{error_total} 个错误待修复）|")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, gate in enumerate(report.gate_results):
        icon = "✅" if gate.passed else "❌"
        gate_info = {
            'structure_integrity': '文件结构',
            'citation_bib_consistency': '引用匹配',
            'reference_authenticity': '引文真实性',
            'figure_table_crossref': '图表交叉引用',
            'data_integrity': '数据完整性',
            'writing_quality': '写作质量',
        }
        name = gate_info.get(gate.gate_name, gate.gate_name)
        lines.append(f"## {icon} 关卡 {i+1}: {name}")
        lines.append(f"")
        lines.append(f"- 得分: **{gate.score:.0f}/100**")
        lines.append(f"- 摘要: {gate.summary}")

        # Show dismissed issues for this gate
        gate_dismissed = [d for d in report.dismissed_issues if d.gate_name == gate.gate_name]
        if gate_dismissed:
            lines.append(f"")
            lines.append(f"### ⚠️ 学生标记为非问题（{len(gate_dismissed)} 项）")
            lines.append(f"")
            for d in gate_dismissed:
                lines.append(f"- ❓ {d.original_message}")
                lines.append(f"  - 💬 学生理由: \"{d.reason}\"")
                lines.append(f"  - 👉 **导师请核实**")

        # Show unresolved errors
        unresolved = [
            issue for idx, issue in enumerate(gate.issues)
            if issue.severity == Severity.ERROR
            and not any(d.gate_name == gate.gate_name and d.issue_index == idx
                       for d in report.dismissed_issues)
        ]
        if unresolved:
            lines.append(f"")
            lines.append(f"### ❌ 未解决的问题 ({len(unresolved)} 个)")
            lines.append(f"")
            for issue in unresolved[:10]:
                lines.append(f"- {issue.message}")
            if len(unresolved) > 10:
                lines.append(f"- ... 还有 {len(unresolved)-10} 个")

        lines.append("")

    # Writing tips section
    writing_gate = next((g for g in report.gate_results if g.gate_name == "writing_quality"), None)
    if writing_gate and writing_gate.metadata and writing_gate.metadata.get("tips"):
        lines.append("## 写作建议")
        lines.append("")
        for tip in writing_gate.metadata["tips"]:
            lines.append(f"- {tip}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by ScholarLint · 投稿通 | https://scholarlint.com*")
    lines.append("")
    lines.append("*此报告供导师审核使用。标记为 ⚠️ 的项目需要导师确认。*")
    lines.append("")

    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


# ─── Bib Cleaning Tools ──────────────────────────────────────

@router.post("/bib-clean/{job_id}")
async def clean_bib(job_id: str, request: Request):
    """Clean and sort the .bib file. Actions: clean, sort, separate_unused."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    action = body.get("action", "clean")  # clean | sort | separate_unused | all

    from app.tools.bib_cleaner import clean_bib_text, sort_bib_by_citation_order, separate_unused, deduplicate_entries
    from app.parsers.tex_parser import parse_all_tex_files

    # Find bib files
    bib_files = list(project_dir.rglob("*.bib"))
    if not bib_files:
        raise HTTPException(status_code=404, detail="No .bib file found")

    # Parse tex files for citation order
    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    results = {}
    for bib_path in bib_files:
        if bib_path.name == "unused.bib":
            continue
        original = bib_path.read_text(encoding="utf-8", errors="replace")
        rel_path = str(bib_path.relative_to(project_dir)).replace("\\", "/")

        if action == "clean":
            cleaned = clean_bib_text(original)
            bib_path.write_text(cleaned, encoding="utf-8")
            results[rel_path] = {"action": "cleaned", "size_before": len(original), "size_after": len(cleaned)}

        elif action == "sort":
            sorted_text = sort_bib_by_citation_order(original, tex_files)
            bib_path.write_text(sorted_text, encoding="utf-8")
            results[rel_path] = {"action": "sorted_by_citation_order"}

        elif action == "separate_unused":
            used_text, unused_text = separate_unused(original, tex_files)
            bib_path.write_text(used_text, encoding="utf-8")
            if unused_text:
                unused_path = bib_path.parent / "unused.bib"
                unused_path.write_text(unused_text, encoding="utf-8")
                results[rel_path] = {"action": "separated", "unused_file": "unused.bib", "unused_entries": unused_text.count("@")}
            else:
                results[rel_path] = {"action": "no_unused_entries"}

        elif action == "all":
            # Full cleanup: clean → sort → separate
            cleaned = clean_bib_text(original)
            deduped, num_removed = deduplicate_entries(cleaned)
            sorted_text = sort_bib_by_citation_order(deduped, tex_files)
            used_text, unused_text = separate_unused(sorted_text, tex_files)
            bib_path.write_text(used_text, encoding="utf-8")
            if unused_text:
                unused_path = bib_path.parent / "unused.bib"
                unused_path.write_text(unused_text, encoding="utf-8")
            results[rel_path] = {
                "action": "full_cleanup",
                "size_before": len(original),
                "size_after": len(used_text),
                "duplicates_removed": num_removed,
                "unused_entries": unused_text.count("@") if unused_text else 0,
            }

    return {"status": "done", "results": results}


@router.get("/fetch-bib/{doi:path}")
async def fetch_official_bib(doi: str):
    """Fetch the official .bib entry from DBLP/ACL for a given DOI."""
    import httpx

    # Try DBLP first (covers most CS venues)
    sources = [
        f"https://dblp.org/doi/{doi}.bib",
    ]

    from app.tools.bib_cleaner import clean_bib_text

    # ACL Anthology
    if "10.18653" in doi:
        acl_id = doi.split("/")[-1]
        sources.insert(0, f"https://aclanthology.org/{acl_id}.bib")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in sources:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and "@" in resp.text:
                    cleaned = clean_bib_text(resp.text.strip())
                    return {"status": "found", "source": url, "bib": cleaned.strip()}
            except Exception:
                continue

    # Fallback: Crossref formatted citation
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex",
                headers={"User-Agent": "IntegrityAssurance/0.1"},
            )
            if resp.status_code == 200 and "@" in resp.text:
                    cleaned = clean_bib_text(resp.text.strip())
                    return {"status": "found", "source": "crossref", "bib": cleaned.strip()}
    except Exception:
        pass

    return {"status": "not_found", "doi": doi}


# ─── Project Tidy Up ─────────────────────────────────────────

@router.get("/tidyup/{job_id}")
async def analyze_tidyup_changes(job_id: str):
    """Analyze what tidy-up changes would be made (preview only)."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.tools.tidyup import analyze_tidyup
    from app.parsers.tex_parser import parse_all_tex_files

    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    changes = analyze_tidyup(project_dir, tex_files)
    return {"changes": [
        {"type": c["type"], "description": c["description"], "source": c["source"], "target": c["target"]}
        for c in changes
    ]}


@router.post("/tidyup/{job_id}")
async def execute_tidyup(job_id: str, request: Request):
    """Execute selected tidy-up changes."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    selected_indices = body.get("selected", [])  # list of indices to execute

    from app.tools.tidyup import analyze_tidyup, execute_changes
    from app.parsers.tex_parser import parse_all_tex_files

    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    all_changes = analyze_tidyup(project_dir, tex_files)

    # Filter to selected only
    selected_changes = [all_changes[i] for i in selected_indices if i < len(all_changes)]
    executed = execute_changes(project_dir, selected_changes)

    return {"status": "done", "executed": executed, "count": len(executed)}


# ─── Format Normalization ────────────────────────────────────

@router.post("/format-normalize/{job_id}")
async def format_normalize(job_id: str, request: Request):
    """Auto-fix formatting inconsistencies in .tex files."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    file_path = body.get("file")  # specific file, or None for all
    rules = body.get("rules")  # specific rules, or None for all

    from app.tools.format_normalizer import normalize_format

    all_changes = []
    targets = []

    if file_path:
        target = (project_dir / file_path).resolve()
        # Path traversal check: must stay within project_dir
        if not str(target).startswith(str(project_dir.resolve())):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if target.exists() and target.suffix == ".tex":
            targets.append(target)
    else:
        targets = list(project_dir.rglob("*.tex"))

    for target in targets:
        content = target.read_text(encoding="utf-8")
        normalized, changes = normalize_format(content, rules)
        if changes:
            target.write_text(normalized, encoding="utf-8")
            all_changes.extend([f"[{target.name}] {c}" for c in changes])

    return {
        "status": "ok",
        "changes": all_changes,
        "files_modified": len([t for t in targets if any(t.name in c for c in all_changes)]),
    }


# ─── AI-Powered Fix Suggestions ──────────────────────────────

@router.post("/ai-fix/{job_id}")
async def ai_fix_suggestion(job_id: str, request: Request):
    """Use LLM to suggest a fix for a specific issue."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    issue_message = body.get("message", "")
    file_path = body.get("file", "")
    line_num = body.get("line")
    context = body.get("context", "")  # surrounding code
    gate_name = body.get("gate", "")

    if not issue_message:
        raise HTTPException(status_code=400, detail="Missing issue message")

    # Integrity guardrail: never let the LLM "fix" a fabricated/unverifiable
    # reference — it would just hallucinate another fake citation. Do not
    # generate any AI suggestion for these issues.
    if _is_reference_authenticity_issue(gate_name, issue_message):
        return {
            "status": "not_fixable",
            "detail": (
                "文献真实性/缺少可信来源的问题不提供 AI 建议修复。"
                "请删除该引用，或替换为可在 Crossref / Semantic Scholar / OpenAlex "
                "等权威来源核实的真实文献；不要使用 AI 编造 BibTeX。"
            ),
        }

    # Get file context if available
    if file_path and not context:
        target = project_dir / file_path
        if target.exists():
            lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
            if line_num and line_num > 0:
                start = max(0, line_num - 5)
                end = min(len(lines), line_num + 5)
                context = "\n".join(lines[start:end])
            else:
                context = "\n".join(lines[:20])

    # Call LLM — output language must match the paper's own language
    lang = _detect_lang(context, issue_message)
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

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await _llm_chat_post(
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
                suggestion = _strip_code_fence(data["choices"][0]["message"]["content"])
                return {"status": "ok", "suggestion": suggestion, "original": context, "file": file_path}
            else:
                return {"status": "error", "detail": f"LLM API returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-batch-fix/{job_id}")
async def ai_batch_fix(job_id: str, request: Request):
    """Batch AI fix: attempt to fix all auto-fixable issues at once."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Collect fixable issues (errors with file+line info)
    fixable = []
    for gate in report.gate_results:
        # Integrity guardrail: never auto-fix reference authenticity issues —
        # the LLM would fabricate a replacement (another fake citation).
        if gate.gate_name == "reference_authenticity":
            continue
        for idx, issue in enumerate(gate.issues):
            if issue.severity != Severity.ERROR:
                continue
            if _is_reference_authenticity_issue(gate.gate_name, issue.message):
                continue
            # Skip if dismissed
            if any(d.gate_name == gate.gate_name and d.issue_index == idx
                   for d in report.dismissed_issues):
                continue
            if issue.file and issue.line:
                fixable.append({
                    "message": issue.message,
                    "file": issue.file,
                    "line": issue.line,
                    "suggestion": issue.suggestion or "",
                })

    if not fixable:
        return {"status": "ok", "fixes": [], "message": "没有可自动修复的问题"}

    # Batch: get context for each fixable issue and call LLM
    import httpx
    fixes = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in fixable[:5]:  # Limit to 5 at a time to avoid timeout
            target = project_dir / item["file"]
            if not target.exists():
                continue
            lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
            start = max(0, item["line"] - 4)
            end = min(len(lines), item["line"] + 4)
            context = "\n".join(lines[start:end])

            lang = _detect_lang(context, item["message"])
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
                resp = await _llm_chat_post(
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
                    fix_text = _strip_code_fence(data["choices"][0]["message"]["content"])
                    fixes.append({
                        "file": item["file"],
                        "line": item["line"],
                        "message": item["message"],
                        "original": context,
                        "fixed": fix_text,
                    })
            except Exception:
                continue

    return {"status": "ok", "fixes": fixes, "total_fixable": len(fixable)}


@router.post("/ai-review/{job_id}")
async def ai_reviewer_simulation(job_id: str, request: Request):
    """Simulate a peer reviewer reading the paper — identify weaknesses and questions."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get main tex content (first 3000 chars for efficiency)
    main_text = ""
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            main_text = content[:8000]
            break
    if not main_text:
        return {"status": "error", "detail": "No main .tex found"}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await _llm_chat_post(
                client,
                [
                    {"role": "system", "content": """你是一位严格的顶会审稿人（ACL/NeurIPS/ICML level）。
请阅读以下论文片段，给出：
1. **Strengths** (2-3 点，简洁)
2. **Weaknesses** (3-5 点，具体且可操作)
3. **Questions for Authors** (2-3 个关键问题)
4. **Overall Score**: Accept / Borderline / Reject

用中文回复，格式清晰。每点用 - 开头。注意：你应该像真正的审稿人一样严格但公正。"""},
                    {"role": "user", "content": f"请审阅这篇论文:\n\n{main_text}"},
                ],
                max_tokens=1000,
                temperature=0.7,
            )
            if resp.status_code == 200:
                data = resp.json()
                review = data["choices"][0]["message"]["content"].strip()
                return {"status": "ok", "review": review}
            else:
                return {"status": "error", "detail": f"LLM API returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-polish/{job_id}")
async def ai_polish_text(job_id: str, request: Request):
    """Polish a selected paragraph to be more academic and fluent."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    text = body.get("text", "")
    mode = body.get("mode", "academic")  # 'academic' | 'concise' | 'formal'

    if not text or len(text) < 10:
        raise HTTPException(status_code=400, detail="请选择要润色的文本")

    mode_prompts = {
        "academic": "改写为更加学术化、流畅的英文表达，保持原意不变。使用学术论文常见的表达方式。",
        "concise": "精简这段文字，去除冗余表达，使其更加简洁有力，同时保留所有关键信息。",
        "formal": "改写为更正式的学术写作风格，避免口语化表达，使用被动语态和正式词汇。",
    }
    prompt = mode_prompts.get(mode, mode_prompts["academic"])

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await _llm_chat_post(
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
            else:
                return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-abstract/{job_id}")
async def ai_optimize_abstract(job_id: str, request: Request):
    """Optimize the paper's abstract based on full content analysis."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    # Extract abstract and paper content
    main_text = ""
    abstract = ""
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            main_text = content[:6000]
            import re
            abs_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", content, re.DOTALL)
            if abs_match:
                abstract = abs_match.group(1).strip()
            break

    if not abstract:
        return {"status": "error", "detail": "未找到 abstract"}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await _llm_chat_post(
                client,
                [
                    {"role": "system", "content": """你是一位学术写作专家。请优化这篇论文的 Abstract，使其：
1. 更加简洁有力（控制在 150-250 词）
2. 结构清晰：问题→方法→结果→结论
3. 突出贡献和创新点
4. 使用主动语态和强动词

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
            else:
                return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


# ─── Reproducibility Checklist ───────────────────────────────

REPRODUCIBILITY_CHECKLIST = [
    {"id": "C1", "section": "Code & Models", "text": "Is the source code provided, or will it be released, with instructions to reproduce the main results?"},
    {"id": "C2", "section": "Code & Models", "text": "Are software dependencies and the run environment (library versions, hardware) specified?"},
    {"id": "C3", "section": "Code & Models", "text": "Is the model architecture and all of its components clearly described?"},
    {"id": "C4", "section": "Code & Models", "text": "Are pretrained models or checkpoints made available where applicable?"},
    {"id": "D1", "section": "Datasets", "text": "Are all datasets described (source, size, and license)?"},
    {"id": "D2", "section": "Datasets", "text": "Are data preprocessing, filtering, and cleaning steps described?"},
    {"id": "D3", "section": "Datasets", "text": "Are dataset access instructions or download links provided?"},
    {"id": "D4", "section": "Datasets", "text": "Are train/validation/test splits clearly defined?"},
    {"id": "E1", "section": "Experimental Results", "text": "Are all hyperparameters and how they were selected reported?"},
    {"id": "E2", "section": "Experimental Results", "text": "Is the computing infrastructure (hardware, memory, runtime) reported?"},
    {"id": "E3", "section": "Experimental Results", "text": "Are results reported with both central tendency and variation (e.g., mean ± std over multiple runs)?"},
    {"id": "E4", "section": "Experimental Results", "text": "Is the number of runs and/or random seeds reported?"},
    {"id": "E5", "section": "Experimental Results", "text": "Are all evaluation metrics clearly defined?"},
    {"id": "E6", "section": "Experimental Results", "text": "Are statistical significance tests reported where appropriate?"},
    {"id": "T1", "section": "Theoretical Claims", "text": "Are all assumptions stated and complete proofs provided for any theoretical claims?"},
]


@router.post("/venue-checklist/{job_id}")
async def generate_venue_checklist(job_id: str, request: Request):
    """AI auto-fill the Reproducibility Checklist based on paper content."""
    _llm_usage_guard(request)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    checklist = REPRODUCIBILITY_CHECKLIST

    # Get paper content
    main_text = ""
    for f in project_dir.rglob("*.tex"):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "\\documentclass" in content:
            main_text = content[:10000]
            break

    if not main_text:
        return {"status": "error", "detail": "No main .tex found"}

    # Build prompt
    checklist_str = "\n".join([f"- [{item['id']}] {item['text']}" for item in checklist])

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await _llm_chat_post(
                client,
                [
                    {"role": "system", "content": f"""You are an academic reproducibility assistant helping authors fill out a Reproducibility Checklist for their paper.

For each checklist item, determine:
- "yes": The paper addresses this. Provide the EXACT section/paragraph reference (e.g., "Section 5, paragraph 2")
- "no": The paper does NOT address this. Write a brief justification the author can paste directly into the checklist.
- "na": Not applicable. Explain why in one sentence.

IMPORTANT: The justification must be a complete sentence that can be directly pasted into the submission form. Write in English (this is for conference submission).

Examples:
- {{"id":"C1","answer":"yes","justification":"We release our source code at the anonymized repository linked in Section 1, with a README describing how to reproduce all results."}}
- {{"id":"E3","answer":"no","justification":"We report only single-run results; we will add mean and standard deviation over multiple seeds."}}
- {{"id":"T1","answer":"na","justification":"Our work is empirical and contains no theoretical claims requiring proofs."}}

Output as JSON array."""},
                    {"role": "user", "content": f"Checklist items:\n{checklist_str}\n\nPaper content:\n{main_text[:6000]}"},
                ],
                max_tokens=3000,
                temperature=0.2,
            )
            if resp.status_code == 200:
                data = resp.json()
                result_text = data["choices"][0]["message"]["content"].strip()
                # Parse JSON from response
                import json
                # Try to extract JSON array
                json_match = result_text
                if "```" in json_match:
                    json_match = json_match.split("```")[1].replace("json", "").strip()
                try:
                    answers = json.loads(json_match)
                except json.JSONDecodeError:
                    answers = []

                # Merge answers with checklist items
                result = []
                for item in checklist:
                    answer_data = next((a for a in answers if a.get("id") == item["id"]), None)
                    result.append({
                        **item,
                        "answer": answer_data.get("answer", "unknown") if answer_data else "unknown",
                        "justification": answer_data.get("justification", answer_data.get("reason", "")) if answer_data else "",
                    })

                return {"status": "ok", "venue": "reproducibility", "checklist": result}
            else:
                return {"status": "error", "detail": f"LLM returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


# ─── History & Cleanup ────────────────────────────────────────

@router.get("/history")
async def get_history():
    """Return list of recent jobs for the history panel."""
    return {"jobs": storage.list_jobs(limit=50)}


@router.get("/compare/{job_id}")
async def compare_with_previous(job_id: str):
    """Compare current check results with the previous check of the same file."""
    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Find previous check of same filename
    all_jobs = storage.list_jobs(limit=50)
    same_file = [j for j in all_jobs if j["filename"] == report.filename and j["job_id"] != job_id]
    same_file.sort(key=lambda x: x["timestamp"], reverse=True)

    if not same_file:
        return {"has_previous": False}

    prev_job = same_file[0]
    prev_report = storage.load_report(prev_job["job_id"])
    if not prev_report:
        return {"has_previous": False}

    # Compute diff
    curr_errors = sum(len([i for i in g.issues if i.severity == Severity.ERROR]) for g in report.gate_results)
    prev_errors = sum(len([i for i in g.issues if i.severity == Severity.ERROR]) for g in prev_report.gate_results)
    curr_warnings = sum(len([i for i in g.issues if i.severity == Severity.WARNING]) for g in report.gate_results)
    prev_warnings = sum(len([i for i in g.issues if i.severity == Severity.WARNING]) for g in prev_report.gate_results)

    gate_diffs = []
    for curr_gate in report.gate_results:
        prev_gate = next((g for g in prev_report.gate_results if g.gate_name == curr_gate.gate_name), None)
        if prev_gate:
            gate_diffs.append({
                "gate": curr_gate.gate_name,
                "curr_passed": curr_gate.passed,
                "prev_passed": prev_gate.passed,
                "curr_score": curr_gate.score,
                "prev_score": prev_gate.score,
                "improved": curr_gate.score > prev_gate.score,
            })

    return {
        "has_previous": True,
        "previous_job_id": prev_job["job_id"],
        "previous_timestamp": prev_job["timestamp"],
        "score_diff": report.overall_score - prev_report.overall_score,
        "curr_score": report.overall_score,
        "prev_score": prev_report.overall_score,
        "error_diff": curr_errors - prev_errors,
        "warning_diff": curr_warnings - prev_warnings,
        "gates": gate_diffs,
    }


@router.get("/score-trend/{job_id}")
async def get_score_trend(job_id: str):
    """Return score history for the same filename as the given job.

    Useful for showing improvement trend across multiple checks.
    """
    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    all_jobs = storage.list_jobs(limit=50)
    # Filter to same filename, sorted chronologically
    same_file = [j for j in all_jobs if j["filename"] == report.filename]
    same_file.sort(key=lambda x: x["timestamp"])

    trend = [{
        "job_id": j["job_id"],
        "score": j["score"],
        "timestamp": j["timestamp"],
        "gates_passed": j["gates_passed"],
        "gates_total": j["gates_total"],
    } for j in same_file]

    return {"filename": report.filename, "trend": trend}


@router.get("/analysis/{job_id}")
async def get_analysis(job_id: str):
    """Return detailed analysis: section word counts + citation year distribution."""
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    report = _get_report(job_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # 1. Section word counts
    import re
    sections = []
    for f in project_dir.rglob("*.tex"):
        text = f.read_text(encoding="utf-8", errors="replace")
        # Remove comments
        text = re.sub(r"%.*", "", text)
        # Find sections
        sec_pattern = re.compile(
            r"\\(section|subsection|subsubsection)\{([^}]+)\}"
        )
        matches = list(sec_pattern.finditer(text))
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = text[start:end]
            # Strip LaTeX commands for word count
            clean = re.sub(r"\\[a-zA-Z]+(\{[^}]*\})*", " ", chunk)
            clean = re.sub(r"[{}\\$%&~^_]", " ", clean)
            words = len([w for w in clean.split() if len(w) > 1])
            level = {"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)]
            sections.append({
                "title": m.group(2).strip(),
                "level": level,
                "words": words,
            })

    # 2. Citation year distribution
    year_dist = {}
    ref_gate = next(
        (g for g in report.gate_results if g.gate_name == "reference_authenticity"),
        None,
    )
    if ref_gate and ref_gate.metadata:
        entries = ref_gate.metadata.get("verified_entries", [])
        for entry in entries:
            year = entry.get("year")
            if year and isinstance(year, int) and 1900 < year < 2100:
                year_dist[year] = year_dist.get(year, 0) + 1

    # Compute stats
    years = []
    for y, count in year_dist.items():
        years.extend([y] * count)
    median_year = sorted(years)[len(years) // 2] if years else None
    recent_count = sum(1 for y in years if y >= 2022)
    recent_pct = (recent_count / len(years) * 100) if years else 0

    return {
        "sections": sections,
        "citation_years": dict(sorted(year_dist.items())),
        "citation_stats": {
            "total": len(years),
            "median_year": median_year,
            "recent_pct": round(recent_pct, 1),
            "oldest": min(years) if years else None,
            "newest": max(years) if years else None,
        },
    }


@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its files permanently."""
    # Remove from memory
    _jobs.pop(job_id, None)
    _job_status.pop(job_id, None)
    _job_dirs.pop(job_id, None)
    # Remove from disk
    deleted = storage.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


# ─── Internal helpers ─────────────────────────────────────────

async def _run_checks(job_id: str, zip_path: Path, extract_dir: Path, filename: str):
    """Extract zip and run checks."""
    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
        project_dir = extract_zip(zip_path, extract_dir)
        _job_dirs[job_id] = project_dir

        # Security scan: check for suspicious files
        _DANGEROUS_EXTS = {'.exe', '.bat', '.cmd', '.sh', '.ps1', '.dll', '.so', '.msi', '.com', '.vbs', '.js'}
        for f in project_dir.rglob("*"):
            if f.is_file():
                if f.suffix.lower() in _DANGEROUS_EXTS:
                    f.unlink()  # Remove dangerous files silently
                elif f.stat().st_size > 50 * 1024 * 1024:  # >50MB single file
                    f.unlink()  # Remove oversized files

        await _run_checks_from_dir(job_id, project_dir, filename, [])
    except Exception as e:
        _job_status[job_id] = "failed"
        _jobs[job_id] = FullReport(
            job_id=job_id, filename=filename,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        logger.error(f" Job {job_id} failed: {redact(str(e))}")
    finally:
        if zip_path.exists():
            zip_path.unlink()


async def _run_checks_from_dir(
    job_id: str, project_dir: Path, filename: str,
    old_dismissed: list[DismissedIssue],
):
    """Run checks from an already-extracted directory."""
    try:
        from app.parsers.zip_parser import identify_project_structure

        paper, tex_paths, bib_paths = identify_project_structure(project_dir)
        paper.tex_files = parse_all_tex_files(tex_paths)
        paper.bib_entries = parse_all_bib_files(bib_paths)

        gates = [
            StructureGate(),
            CitationConsistencyGate(),
            ReferenceAuthenticityGate(),
            FigureTableGate(),
            DataIntegrityGate(),
            WritingQualityGate(),
        ]

        report = FullReport(
            job_id=job_id,
            filename=filename,
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_dir=str(project_dir),
            dismissed_issues=old_dismissed,
        )

        _job_progress[job_id] = []

        for gate in gates:
            result = await gate.check(paper)
            report.gate_results.append(result)
            _job_progress[job_id].append(gate.name)

        # Compute paper stats
        import re as _re
        total_words = 0
        for tf in paper.tex_files:
            # Strip LaTeX commands and count words
            text = _re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", tf.raw_text)
            text = _re.sub(r"\\[a-zA-Z]+", "", text)
            text = _re.sub(r"[{}$%\\]", "", text)
            total_words += len(text.split())

        report.metadata = {
            "word_count": total_words,
            "page_estimate": round(total_words / 500, 1),  # ~500 words/page for ACL format
            "bib_count": len(paper.bib_entries),
            "tex_count": len(paper.tex_files),
        }

        report.compute_overall()
        _jobs[job_id] = report
        _job_status[job_id] = "completed"
        _persist(job_id)

    except Exception as e:
        _job_status[job_id] = "failed"
        logger.error(f" Recheck {job_id} failed: {redact(str(e))}")
