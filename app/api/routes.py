"""API routes for integrity checks + file editor + human-in-the-loop."""

import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Request, Response
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
_job_owners: dict[str, dict] = {}  # job_id → owner/share metadata while processing

SESSION_COOKIE_NAME = "sl_session"
SESSION_COOKIE_MAX_AGE = 30 * 86400


def _request_share_token(request: Request) -> str:
    """Read share token from query string or header."""
    return (
        request.query_params.get("share")
        or request.headers.get("X-Share-Token")
        or ""
    ).strip()


def _set_session_cookie_if_needed(response: Response | None, session_id: str) -> None:
    """Persist a generated anonymous session id in an httpOnly cookie."""
    if response is None:
        return
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=False,  # Set True behind HTTPS in production.
        max_age=SESSION_COOKIE_MAX_AGE,
        samesite="lax",
    )


async def _get_request_owner(
    request: Request,
    response: Response | None = None,
    current_user=None,
) -> dict:
    """Return the authenticated user owner or anonymous session owner."""
    if current_user is None:
        from app.dependencies import get_current_user_optional

        current_user = await get_current_user_optional(request)

    if current_user:
        return {"owner_type": "user", "owner_id": str(current_user.id)}

    session_id = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if not session_id:
        session_id = secrets.token_urlsafe(32)
        _set_session_cookie_if_needed(response, session_id)
    return {"owner_type": "session", "owner_id": session_id, "session_id": session_id}


def _new_share_token() -> str:
    return secrets.token_urlsafe(24)


def _owner_metadata(owner: dict, share_token: str | None = None) -> dict:
    metadata = {
        "owner_type": owner["owner_type"],
        "owner_id": owner["owner_id"],
        "share_token": share_token or _new_share_token(),
    }
    if owner.get("session_id"):
        metadata["session_id"] = owner["session_id"]
    return metadata


def _extract_owner_metadata(report_or_metadata) -> dict:
    metadata = getattr(report_or_metadata, "metadata", report_or_metadata) or {}
    return {
        "owner_type": metadata.get("owner_type"),
        "owner_id": metadata.get("owner_id"),
        "session_id": metadata.get("session_id"),
        "share_token": metadata.get("share_token"),
    }


async def _owner_metadata_allows(
    metadata: dict,
    request: Request,
    response: Response | None = None,
    *,
    write: bool = False,
    allow_share: bool = True,
) -> bool:
    owner_type = metadata.get("owner_type")
    owner_id = metadata.get("owner_id")
    share_token = metadata.get("share_token")

    # Legacy reports created before ownership metadata remain readable/writable
    # for local demo compatibility.
    if not owner_type or not owner_id:
        return True

    request_owner = await _get_request_owner(request, response)
    if request_owner["owner_type"] == owner_type and request_owner["owner_id"] == str(owner_id):
        return True

    request_share = _request_share_token(request)
    if allow_share and request_share and share_token and secrets.compare_digest(request_share, str(share_token)):
        return not write

    return False


async def _can_access_report(
    report: FullReport,
    request: Request,
    response: Response | None = None,
    *,
    mode: str = "read",
    allow_share: bool = True,
) -> bool:
    return await _owner_metadata_allows(
        _extract_owner_metadata(report),
        request,
        response,
        write=(mode == "write"),
        allow_share=allow_share,
    )


async def _require_job_access(
    job_id: str,
    request: Request,
    response: Response | None = None,
    *,
    write: bool = False,
    allow_share: bool = True,
) -> FullReport | None:
    """Require read/write access to a job; returns report when one exists."""
    report = _get_report(job_id)
    if report:
        if not await _can_access_report(
            report,
            request,
            response,
            mode="write" if write else "read",
            allow_share=allow_share,
        ):
            raise HTTPException(status_code=403, detail="Access denied")
        return report

    owner_metadata = _job_owners.get(job_id)
    if owner_metadata:
        if not await _owner_metadata_allows(
            owner_metadata,
            request,
            response,
            write=write,
            allow_share=allow_share,
        ):
            raise HTTPException(status_code=403, detail="Access denied")
        return None

    if job_id in _job_status:
        return None
    raise HTTPException(status_code=404, detail="Job not found")


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
        owner_metadata = _extract_owner_metadata(report)
        if owner_metadata.get("owner_type") and owner_metadata.get("owner_id"):
            _job_owners[job_id] = owner_metadata
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


def _ai_fix_provenance(gate_name: str, file_path: str, line_num, context: str) -> dict:
    """Return audit metadata for an AI suggestion."""
    return {
        "source": "llm",
        "model": settings.llm_model,
        "gate": gate_name,
        "file": file_path or None,
        "line": line_num,
        "context_chars": len(context or ""),
    }


def _not_fixable_reference_payload(issue_message: str, gate_name: str = "") -> dict:
    """Standard response for reference issues that must not be LLM-fixed."""
    return {
        "status": "not_fixable",
        "not_fixable": True,
        "risk": "high",
        "requires_manual_review": True,
        "provenance": {
            "source": "rule",
            "gate": gate_name or "reference_authenticity",
            "reason": "reference_authenticity_guardrail",
        },
        "detail": (
            "文献真实性/缺少可信来源的问题不提供 AI 建议修复。"
            "请删除该引用，或替换为可在 Crossref / Semantic Scholar / OpenAlex "
            "等权威来源核实的真实文献；不要使用 AI 编造 BibTeX。"
        ),
        "candidate_search_available": True,
        "issue": issue_message,
    }


def _safe_project_file(
    project_dir: Path,
    file_path: str,
    *,
    allowed_suffixes: tuple[str, ...] | None = None,
) -> Path:
    """Resolve a project-relative path and guarantee it stays in project_dir."""
    target = (project_dir / file_path).resolve()
    try:
        target.relative_to(project_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if allowed_suffixes and target.suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=403, detail="Unsupported file type")
    return target


def _extract_reference_title(*texts: str) -> str:
    """Best-effort extraction of a reference title from issue/evidence text."""
    import re

    blob = "\n".join(t for t in texts if t)
    patterns = [
        r"标题[:：]\s*(.+)",
        r"title[:：]\s*(.+)",
        r"\\btitle\\s*=\\s*[{\"]([^}\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("{}\"'.,;")[:300]
    return ""


def _candidate_from_crossref(item: dict) -> dict:
    title = (item.get("title") or [""])[0]
    authors = [
        " ".join(p for p in [a.get("given", ""), a.get("family", "")] if p).strip()
        for a in item.get("author", [])[:5]
    ]
    year_parts = (item.get("issued") or {}).get("date-parts") or []
    year = year_parts[0][0] if year_parts and year_parts[0] else None
    doi = item.get("DOI")
    return {
        "source": "crossref",
        "title": title,
        "authors": [a for a in authors if a],
        "year": year,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else item.get("URL"),
        "score": item.get("score"),
    }


def _candidate_from_s2(item: dict) -> dict:
    return {
        "source": "semantic_scholar",
        "title": item.get("title"),
        "authors": [a.get("name") for a in item.get("authors", [])[:5] if a.get("name")],
        "year": item.get("year"),
        "doi": item.get("externalIds", {}).get("DOI"),
        "url": item.get("url"),
        "score": None,
    }


def _candidate_from_openalex(item: dict) -> dict:
    doi = item.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")
    return {
        "source": "openalex",
        "title": item.get("display_name"),
        "authors": [
            a.get("author", {}).get("display_name")
            for a in item.get("authorships", [])[:5]
            if a.get("author", {}).get("display_name")
        ],
        "year": item.get("publication_year"),
        "doi": doi,
        "url": item.get("id"),
        "score": item.get("relevance_score"),
    }


# ─── Upload & Check ───────────────────────────────────────────

@router.post("/upload")
async def upload_paper(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
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
    owner = await _get_request_owner(request, response, current_user=user)
    owner_metadata = _owner_metadata(owner)

    with open(upload_path, "wb") as f:
        f.write(content)

    _job_status[job_id] = "processing"
    _job_owners[job_id] = owner_metadata
    background_tasks.add_task(_run_checks, job_id, upload_path, extract_dir, file.filename, owner_metadata)

    return {"job_id": job_id, "status": "processing", "share_token": owner_metadata["share_token"]}


@router.get("/status/{job_id}")
async def get_status(job_id: str, request: Request, response: Response):
    await _require_job_access(job_id, request, response)
    status = _job_status.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": status,
        "progress": _job_progress.get(job_id, []),
    }


@router.get("/report/{job_id}")
async def get_report(job_id: str, request: Request, response: Response):
    report = await _require_job_access(job_id, request, response)
    if not report:
        status = _job_status.get(job_id, "not_found")
        if status == "processing":
            raise HTTPException(status_code=202, detail="Still processing")
        raise HTTPException(status_code=404, detail="Report not found")
    return report.model_dump()


# ─── File CRUD (for editor) ───────────────────────────────────

@router.get("/files/{job_id}")
async def list_files(job_id: str, request: Request, response: Response):
    """List all editable files (.tex, .bib) in the project."""
    await _require_job_access(job_id, request, response)
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
async def read_file(job_id: str, file_path: str, request: Request, response: Response):
    """Read a file's content."""
    await _require_job_access(job_id, request, response)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    target = _safe_project_file(project_dir, file_path)
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
async def save_file(job_id: str, file_path: str, request: Request, response: Response):
    """Save file content (auto-save from editor)."""
    await _require_job_access(job_id, request, response, write=True)
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

    target = _safe_project_file(project_dir, file_path, allowed_suffixes=EDITABLE_EXTENSIONS)

    body = await request.body()
    content = body.decode("utf-8")
    target.write_text(content, encoding="utf-8")

    return {"status": "saved", "path": file_path, "size": len(content)}


# ─── Recheck (re-run checks on modified files) ────────────────

@router.post("/recheck/{job_id}")
async def recheck(request: Request, response: Response, job_id: str, background_tasks: BackgroundTasks):
    """Re-run all checks on the (possibly modified) project files."""
    from app.dependencies import get_current_user_optional
    from app.credits import deduct_credits, InsufficientCredits
    from app.database import SessionLocal

    report = await _require_job_access(job_id, request, response, write=True)

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

    filename = report.filename if report else "unknown.zip"

    # Keep dismissed issues from previous run
    old_dismissed = report.dismissed_issues if report else []
    owner_metadata = _extract_owner_metadata(report) if report else _job_owners.get(job_id, {})

    _job_status[job_id] = "processing"
    background_tasks.add_task(_run_checks_from_dir, job_id, project_dir, filename, old_dismissed, owner_metadata)

    return {"job_id": job_id, "status": "processing"}


# ─── Human-in-the-Loop: Dismiss ──────────────────────────────

@router.post("/dismiss/{job_id}")
async def dismiss_issue(job_id: str, request: Request, response: Response):
    """Student dismisses an issue with a reason."""
    report = await _require_job_access(job_id, request, response, write=True)
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
async def export_report(job_id: str, request: Request, response: Response):
    """Export a human-readable report for supervisor review."""
    report = await _require_job_access(job_id, request, response)
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
async def clean_bib(job_id: str, request: Request, response: Response):
    """Clean and sort the .bib file. Actions: clean, sort, separate_unused."""
    await _require_job_access(job_id, request, response, write=True)
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


@router.post("/reference-candidates/{job_id}")
async def search_reference_candidates(job_id: str, request: Request, response: Response):
    """Search authoritative sources for real candidate references.

    This endpoint intentionally does not call the LLM and never fabricates
    bibliography data. It only returns candidates retrieved from public scholarly
    indexes so the author can manually verify and replace a suspect reference.
    """
    await _require_job_access(job_id, request, response, allow_share=False)
    body = await request.json()
    title = (body.get("title") or "").strip()
    if not title:
        title = _extract_reference_title(
            body.get("message", ""),
            body.get("evidence", ""),
            body.get("bibtex", ""),
        )
    if not title or len(title) < 8:
        return {
            "status": "not_found",
            "detail": "未能从问题中提取足够明确的标题，请手动输入标题后再搜索。",
            "candidates": [],
        }

    import httpx

    candidates = []
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={"query.title": title, "rows": 3},
                headers={"User-Agent": f"ScholarLint/5.3 ({settings.crossref_email})"},
            )
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                candidates.extend(_candidate_from_crossref(item) for item in items)
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": title,
                    "limit": 3,
                    "fields": "title,authors,year,url,externalIds",
                },
            )
            if resp.status_code == 200:
                candidates.extend(_candidate_from_s2(item) for item in resp.json().get("data", []))
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={"search": title, "per-page": 3},
            )
            if resp.status_code == 200:
                candidates.extend(_candidate_from_openalex(item) for item in resp.json().get("results", []))
        except Exception:
            pass

    # Deduplicate by DOI/title while preserving source evidence.
    seen = set()
    deduped = []
    for candidate in candidates:
        if not candidate.get("title"):
            continue
        key = (candidate.get("doi") or candidate.get("title", "")).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return {
        "status": "ok" if deduped else "not_found",
        "query": title,
        "candidates": deduped[:8],
        "provenance": {
            "source": "authoritative_search",
            "sources": ["crossref", "semantic_scholar", "openalex"],
            "llm_used": False,
        },
    }


# ─── Project Tidy Up ─────────────────────────────────────────

@router.get("/tidyup/{job_id}")
async def analyze_tidyup_changes(job_id: str, request: Request, response: Response):
    """Analyze what tidy-up changes would be made (preview only)."""
    await _require_job_access(job_id, request, response, write=True)
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
async def execute_tidyup(job_id: str, request: Request, response: Response):
    """Execute selected tidy-up changes."""
    await _require_job_access(job_id, request, response, write=True)
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
async def format_normalize(job_id: str, request: Request, response: Response):
    """Auto-fix formatting inconsistencies in .tex files."""
    await _require_job_access(job_id, request, response, write=True)
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
        target = _safe_project_file(project_dir, file_path, allowed_suffixes=(".tex",))
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
async def ai_fix_suggestion(job_id: str, request: Request, response: Response):
    """Use LLM to suggest a fix for a specific issue."""
    await _require_job_access(job_id, request, response, write=True)
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
        return _not_fixable_reference_payload(issue_message, gate_name)

    # Get file context if available
    if file_path and not context:
        target = _safe_project_file(project_dir, file_path, allowed_suffixes=(".tex", ".bib"))
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
                return {
                    "status": "ok",
                    "suggestion": suggestion,
                    "original": context,
                    "file": file_path,
                    "risk": "medium",
                    "requires_manual_review": True,
                    "provenance": _ai_fix_provenance(gate_name, file_path, line_num, context),
                }
            else:
                return {"status": "error", "detail": f"LLM API returned {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": redact(str(e))[:100]}


@router.post("/ai-batch-fix/{job_id}")
async def ai_batch_fix(job_id: str, request: Request, response: Response):
    """Batch AI fix: attempt to fix all auto-fixable issues at once."""
    await _require_job_access(job_id, request, response, write=True)
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
            target = _safe_project_file(project_dir, item["file"], allowed_suffixes=(".tex", ".bib"))
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
                        "risk": "medium",
                        "requires_manual_review": True,
                        "provenance": _ai_fix_provenance("", item["file"], item["line"], context),
                    })
            except Exception:
                continue

    return {"status": "ok", "fixes": fixes, "total_fixable": len(fixable)}


@router.post("/ai-review/{job_id}")
async def ai_reviewer_simulation(job_id: str, request: Request, response: Response):
    """Simulate a peer reviewer reading the paper — identify weaknesses and questions."""
    await _require_job_access(job_id, request, response, write=True)
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
async def ai_polish_text(job_id: str, request: Request, response: Response):
    """Polish a selected paragraph to be more academic and fluent."""
    await _require_job_access(job_id, request, response, write=True)
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
async def ai_optimize_abstract(job_id: str, request: Request, response: Response):
    """Optimize the paper's abstract based on full content analysis."""
    await _require_job_access(job_id, request, response, write=True)
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

ARR_RESPONSIBLE_NLP_CHECKLIST = [
    {"id": "A1", "section": "A. For every submission", "text": "Did you describe the limitations of your work?"},
    {"id": "A2", "section": "A. For every submission", "text": "Did you discuss any potential risks of your work?"},
    {"id": "B1", "section": "B. Scientific artifacts", "text": "Did you cite the creators of artifacts you used?"},
    {"id": "B2", "section": "B. Scientific artifacts", "text": "Did you discuss the license or terms for use and / or distribution of any artifacts?"},
    {"id": "B3", "section": "B. Scientific artifacts", "text": "Did you discuss if your use of existing artifact(s) was consistent with their intended use, and for artifacts you create, do you specify intended use and whether that is compatible with the original access conditions?"},
    {"id": "B4", "section": "B. Scientific artifacts", "text": "Did you discuss the steps taken to check whether the data that was collected / used contains any information that names or uniquely identifies individual people or offensive content, and the steps taken to protect / anonymize it?"},
    {"id": "B5", "section": "B. Scientific artifacts", "text": "Did you provide documentation of the artifacts, e.g., coverage of domains, languages, linguistic phenomena, demographic groups represented, etc.?"},
    {"id": "B6", "section": "B. Scientific artifacts", "text": "Did you report relevant statistics like the number of examples, details of train / test / dev splits, etc. for the data that you used / created?"},
    {"id": "C1", "section": "C. Computational experiments", "text": "Did you report the number of parameters in the models used, the total computational budget (e.g., GPU hours), and computing infrastructure used?"},
    {"id": "C2", "section": "C. Computational experiments", "text": "Did you discuss the experimental setup, including hyperparameter search and best-found hyperparameter values?"},
    {"id": "C3", "section": "C. Computational experiments", "text": "Did you report descriptive statistics about your results (e.g., error bars around results, summary statistics from sets of experiments), and is it transparent whether you are reporting the max, mean, etc. or just a single run?"},
    {"id": "C4", "section": "C. Computational experiments", "text": "If you used existing packages (e.g., for preprocessing, normalization, or evaluation), did you report the implementation, model, and parameter settings used?"},
    {"id": "D1", "section": "D. Human annotators / participants", "text": "Did you report the full text of instructions given to participants, including e.g., screenshots, disclaimers of any risks to participants or annotators, etc.?"},
    {"id": "D2", "section": "D. Human annotators / participants", "text": "Did you report information about how you recruited and paid participants, and discuss if such payment is adequate given the participants' demographic?"},
    {"id": "D3", "section": "D. Human annotators / participants", "text": "Did you discuss whether and how consent was obtained from people whose data you're using/curating?"},
    {"id": "D4", "section": "D. Human annotators / participants", "text": "Was the data collection protocol approved (or determined exempt) by an ethics review board?"},
    {"id": "D5", "section": "D. Human annotators / participants", "text": "Did you report the basic demographic and geographic characteristics of the annotator population that is the source of the data?"},
    {"id": "E1", "section": "E. AI assistants", "text": "If you used any AI assistants, did you include information about your use?"},
]

NEURIPS_PAPER_CHECKLIST = [
    {"id": "1", "section": "Claims", "text": "Do the main claims made in the abstract and introduction accurately reflect the paper's contributions and scope?"},
    {"id": "2", "section": "Limitations", "text": "Did you discuss the limitations of your work?"},
    {"id": "3", "section": "Theory, Assumptions and Proofs", "text": "If you are including theoretical results, did you state the full set of assumptions of all theoretical results, and did you include complete proofs of all theoretical results?"},
    {"id": "4", "section": "Experimental Result Reproducibility", "text": "If the contribution is a dataset or model, what steps did you take to make your results reproducible or verifiable?"},
    {"id": "5", "section": "Open Access to Data and Code", "text": "If you ran experiments, did you include the code, data, and instructions needed to reproduce the main experimental results (either in the supplemental material or as a URL)?"},
    {"id": "6", "section": "Experimental Setting / Details", "text": "If you ran experiments, did you specify all the training details (e.g., data splits, hyperparameters, how they were chosen)?"},
    {"id": "7", "section": "Experiment Statistical Significance", "text": "Does the paper report error bars suitably and correctly defined or other appropriate information about the statistical significance of the experiments?"},
    {"id": "8", "section": "Experiments Compute Resource", "text": "For each experiment, does the paper provide sufficient information on the computer resources (type of compute workers, memory, time of execution) needed to reproduce the experiments?"},
    {"id": "9", "section": "Code Of Ethics", "text": "Have you read the NeurIPS Code of Ethics and ensured that your research conforms to it?"},
    {"id": "10", "section": "Broader Impacts", "text": "If appropriate for the scope and focus of your paper, did you discuss potential negative societal impacts of your work?"},
    {"id": "11", "section": "Safeguards", "text": "Do you have safeguards in place for responsible release of models with a high risk for misuse (e.g., pretrained language models)?"},
    {"id": "12", "section": "Licenses", "text": "If you are using existing assets (e.g., code, data, models), did you cite the creators and respect the license and terms of use?"},
    {"id": "13", "section": "Assets", "text": "If you are releasing new assets, did you document them and provide these details alongside the assets?"},
    {"id": "14", "section": "Crowdsourcing and Research with Human Subjects", "text": "If you used crowdsourcing or conducted research with human subjects, did you include the full text of instructions given to participants and screenshots, if applicable, as well as details about compensation (if any)?"},
    {"id": "15", "section": "IRB Approvals", "text": "Did you describe any potential participant risks and obtain Institutional Review Board (IRB) approvals (or an equivalent approval/review based on the requirements of your institution), if applicable?"},
    {"id": "16", "section": "Declaration of LLM usage", "text": "Does the paper describe the usage of LLMs if it is an important, original, or non-standard component of the core methods in this research?"},
]

CHECKLISTS = {
    "arr": {
        "name": "ARR Responsible NLP Research Checklist",
        "source": "https://aclrollingreview.org/responsibleNLPresearch/",
        "items": ARR_RESPONSIBLE_NLP_CHECKLIST,
    },
    "neurips": {
        "name": "NeurIPS Paper Checklist",
        "source": "https://neurips.cc/public/guides/PaperChecklist",
        "items": NEURIPS_PAPER_CHECKLIST,
    },
}


@router.post("/venue-checklist/{job_id}")
async def generate_venue_checklist(job_id: str, request: Request, response: Response):
    """AI auto-fill an official ARR / NeurIPS checklist based on paper content."""
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
    checklist_str = "\n".join(
        [f"- [{item['id']}] ({item['section']}) {item['text']}" for item in checklist]
    )

    import httpx
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await _llm_chat_post(
                client,
                [
                    {"role": "system", "content": f"""You are an academic reproducibility assistant helping authors fill out the official {template['name']} for their paper.

For each checklist item, determine:
- "yes": The paper addresses this. Provide the EXACT section/paragraph reference (e.g., "Section 5, paragraph 2")
- "no": The paper does NOT address this. Write a brief justification the author can paste directly into the checklist.
- "na": Not applicable. Explain why in one sentence.

IMPORTANT:
- Use the checklist IDs exactly as provided.
- The justification must be a complete sentence that can be directly pasted into the submission form.
- Write in English (this is for conference submission).
- If the paper is missing evidence, answer "no"; do not infer unstated compliance.

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


# ─── History & Cleanup ────────────────────────────────────────

@router.get("/history")
async def get_history(request: Request, response: Response):
    """Return list of recent jobs for the history panel."""
    owner = await _get_request_owner(request, response)
    return {
        "jobs": storage.list_jobs(
            limit=50,
            owner_type=owner["owner_type"],
            owner_id=owner["owner_id"],
            include_legacy=False,
        )
    }


@router.get("/compare/{job_id}")
async def compare_with_previous(job_id: str, request: Request, response: Response):
    """Compare current check results with the previous check of the same file."""
    report = await _require_job_access(job_id, request, response, allow_share=False)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Find previous check of same filename
    owner = await _get_request_owner(request, response)
    all_jobs = storage.list_jobs(
        limit=50,
        owner_type=owner["owner_type"],
        owner_id=owner["owner_id"],
        include_legacy=False,
    )
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
async def get_score_trend(job_id: str, request: Request, response: Response):
    """Return score history for the same filename as the given job.

    Useful for showing improvement trend across multiple checks.
    """
    report = await _require_job_access(job_id, request, response, allow_share=False)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    owner = await _get_request_owner(request, response)
    all_jobs = storage.list_jobs(
        limit=50,
        owner_type=owner["owner_type"],
        owner_id=owner["owner_id"],
        include_legacy=False,
    )
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
async def get_analysis(job_id: str, request: Request, response: Response):
    """Return detailed analysis: section word counts + citation year distribution."""
    await _require_job_access(job_id, request, response, allow_share=False)
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
async def delete_job(job_id: str, request: Request, response: Response):
    """Delete a job and its files permanently."""
    await _require_job_access(job_id, request, response, write=True, allow_share=False)
    # Remove from memory
    _jobs.pop(job_id, None)
    _job_status.pop(job_id, None)
    _job_dirs.pop(job_id, None)
    _job_owners.pop(job_id, None)
    # Remove from disk
    deleted = storage.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


# ─── Internal helpers ─────────────────────────────────────────

async def _run_checks(job_id: str, zip_path: Path, extract_dir: Path, filename: str, owner_metadata: dict):
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

        await _run_checks_from_dir(job_id, project_dir, filename, [], owner_metadata)
    except Exception as e:
        _job_status[job_id] = "failed"
        _jobs[job_id] = FullReport(
            job_id=job_id, filename=filename,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=owner_metadata,
        )
        logger.error(f" Job {job_id} failed: {redact(str(e))}")
    finally:
        if zip_path.exists():
            zip_path.unlink()


async def _run_checks_from_dir(
    job_id: str, project_dir: Path, filename: str,
    old_dismissed: list[DismissedIssue],
    owner_metadata: dict | None = None,
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
            **(owner_metadata or {}),
        }

        report.compute_overall()
        _jobs[job_id] = report
        _job_owners[job_id] = _extract_owner_metadata(report)
        _job_status[job_id] = "completed"
        _persist(job_id)

    except Exception as e:
        _job_status[job_id] = "failed"
        logger.error(f" Recheck {job_id} failed: {redact(str(e))}")
