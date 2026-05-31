"""API routes for integrity checks + file editor + human-in-the-loop."""

import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.brand_report import build_report_footer, build_report_header
from app.config import settings, LLM_RATE_PER_IP, LLM_RATE_WINDOW, LLM_GLOBAL_HOURLY_CAP
from app.secrets_manager import redact
from app.models import FullReport, DismissedIssue, Severity
from app.parsers.zip_parser import extract_zip
from app.parsers.tex_parser import parse_all_tex_files
from app.parsers.bib_parser import parse_all_bib_files
from app.checks.gate_structure import StructureGate
from app.checks.gate_references import ReferenceAuthenticityGate
from app.checks.gate_citations import CitationConsistencyGate
from app.checks.gate_figures import FigureTableGate
from app.checks.gate_data import DataIntegrityGate
from app.checks.gate_writing import WritingQualityGate
from app.checklists import CHECKLISTS
from app.services.ai_guardrails import (
    ai_fix_provenance as _ai_fix_provenance,
    candidate_from_crossref as _candidate_from_crossref,
    candidate_from_openalex as _candidate_from_openalex,
    candidate_from_s2 as _candidate_from_s2,
    extract_reference_title as _extract_reference_title,
    is_reference_authenticity_issue as _is_reference_authenticity_issue,
    not_fixable_reference_payload as _not_fixable_reference_payload,
)
from app.services.file_store import (
    EDITABLE_EXTENSIONS,
    list_editable_files,
    project_zip_bytes,
    safe_project_file,
)
from app.services.style_analysis import analyze_writing_style
from app import storage
from app.logging_config import logger

router = APIRouter()

__all__ = [
    "_ai_fix_provenance",
    "_candidate_from_crossref",
    "_candidate_from_openalex",
    "_candidate_from_s2",
    "_collect_batch_fix_candidates",
    "_extract_reference_title",
    "_is_reference_authenticity_issue",
    "_not_fixable_reference_payload",
    "router",
]

# In-memory caches (authoritative data is on disk via storage module)
_jobs: dict[str, FullReport] = {}
_job_status: dict[str, str] = {}
_job_dirs: dict[str, Path] = {}  # job_id → extracted project directory
_job_progress: dict[str, list[str]] = {}  # job_id → list of completed gate names
_job_owners: dict[str, dict] = {}  # job_id → owner/share metadata while processing
_job_locks: set[str] = set()  # job_id currently running checks/rechecks

BATCH_FIX_LIMIT = 5
BATCH_FIX_ALLOWED_SUFFIXES = (".tex", ".bib")

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


def _request_uses_valid_share_token(report: FullReport, request: Request) -> bool:
    """Return true only when the request share token matches the report."""
    request_share = _request_share_token(request)
    share_token = _extract_owner_metadata(report).get("share_token")
    if not request_share or not share_token:
        return False
    return secrets.compare_digest(request_share, str(share_token))


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
        _job_status[job_id] = report.metadata.get("status", "completed")
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


def _save_failed_report(job_id: str, filename: str, error: Exception, owner_metadata: dict | None = None) -> None:
    """Persist a failed job report so status survives process restarts."""
    report = FullReport(
        job_id=job_id,
        filename=filename,
        timestamp=datetime.now(timezone.utc).isoformat(),
        overall_passed=False,
        overall_score=0.0,
        metadata={
            "status": "failed",
            "error": redact(str(error))[:300],
            **(owner_metadata or _job_owners.get(job_id, {})),
        },
    )
    _jobs[job_id] = report
    _job_status[job_id] = "failed"
    _job_owners[job_id] = _extract_owner_metadata(report)
    storage.save_report(job_id, report)


def _persist(job_id: str):
    """Save current in-memory report to disk."""
    report = _jobs.get(job_id)
    if report:
        storage.save_report(job_id, report)


# ─── Rate Limiting ────────────────────────────────────────────
_rate_limit: dict[str, list[float]] = {}  # ip → [timestamps]
RATE_LIMIT_MAX = 10  # max uploads per window
RATE_LIMIT_WINDOW = 3600  # 1 hour
_ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


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


def _looks_like_zip(content: bytes) -> bool:
    """Validate ZIP local/central directory magic before writing upload to disk."""
    return any(content.startswith(prefix) for prefix in _ZIP_MAGIC_PREFIXES)


# ─── LLM usage caps (anti-abuse / cost control) ───────────────
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
    if not _looks_like_zip(content):
        raise HTTPException(status_code=400, detail="文件内容不是有效 ZIP（签名校验失败）")

    job_id = uuid.uuid4().hex[:12]  # 12 hex chars = 48 bits entropy
    upload_path = settings.upload_dir / f"{job_id}.zip"
    extract_dir = settings.upload_dir / job_id
    owner = await _get_request_owner(request, response, current_user=user)
    owner_metadata = _owner_metadata(owner)

    with open(upload_path, "wb") as f:
        f.write(content)

    _job_status[job_id] = "processing"
    _job_locks.add(job_id)
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

    return {"files": list_editable_files(project_dir)}


@router.get("/files/{job_id}/{file_path:path}")
async def read_file(job_id: str, file_path: str, request: Request, response: Response):
    """Read a file's content."""
    await _require_job_access(job_id, request, response)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    target = safe_project_file(project_dir, file_path)
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
    if not any(file_path.lower().endswith(ext) for ext in EDITABLE_EXTENSIONS):
        raise HTTPException(status_code=403, detail="只能编辑文本源文件（.tex/.bib/.cls/.sty 等）")

    target = safe_project_file(project_dir, file_path, allowed_suffixes=EDITABLE_EXTENSIONS)

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
    if job_id in _job_locks or _job_status.get(job_id) == "processing":
        raise HTTPException(status_code=409, detail="该任务正在处理中，请等待完成后再重新质检")

    filename = report.filename if report else "unknown.zip"

    # Keep dismissed issues from previous run
    old_dismissed = report.dismissed_issues if report else []
    owner_metadata = _extract_owner_metadata(report) if report else _job_owners.get(job_id, {})

    _job_status[job_id] = "processing"
    _job_locks.add(job_id)
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

    via_share = _request_uses_valid_share_token(report, request)
    lines = build_report_header(
        report,
        job_id,
        exported_at=datetime.now(timezone.utc),
        via_share=via_share,
    ).splitlines()
    lines.append("## 检查概览")
    lines.append("")
    lines.append(f"- 得分: **{report.overall_score:.0f}/100**")

    dismissed_count = len(report.dismissed_issues)
    if report.overall_passed and dismissed_count == 0:
        lines.append("- 总评: 全部通过 — 可安全提交")
    elif report.overall_passed and dismissed_count > 0:
        lines.append(f"- 总评: 通过（{dismissed_count} 项被学生标记为非问题，需导师确认）")
    else:
        error_total = sum(
            sum(1 for iss in g.issues if iss.severity == "error")
            for g in report.gate_results
        )
        lines.append(f"- 总评: 未通过（{error_total} 个错误待修复）")
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
        lines.append("")
        lines.append(f"- 得分: **{gate.score:.0f}/100**")
        lines.append(f"- 摘要: {gate.summary}")

        # Show dismissed issues for this gate
        gate_dismissed = [d for d in report.dismissed_issues if d.gate_name == gate.gate_name]
        if gate_dismissed:
            lines.append("")
            lines.append(f"### ⚠️ 学生标记为非问题（{len(gate_dismissed)} 项）")
            lines.append("")
            for d in gate_dismissed:
                lines.append(f"- ❓ {d.original_message}")
                lines.append(f"  - 💬 学生理由: \"{d.reason}\"")
                lines.append("  - 👉 **导师请核实**")

        # Show unresolved errors
        unresolved = [
            issue for idx, issue in enumerate(gate.issues)
            if issue.severity == Severity.ERROR
            and not any(d.gate_name == gate.gate_name and d.issue_index == idx
                       for d in report.dismissed_issues)
        ]
        if unresolved:
            lines.append("")
            lines.append(f"### ❌ 未解决的问题 ({len(unresolved)} 个)")
            lines.append("")
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

    lines.extend(build_report_footer(via_share=via_share).splitlines())
    lines.append("")

    return PlainTextResponse("\n".join(lines), media_type="text/plain; charset=utf-8")


@router.get("/download/{job_id}")
async def download_project_zip(job_id: str, request: Request, response: Response):
    """Download the current edited project as a ZIP archive."""
    report = await _require_job_access(job_id, request, response)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir or not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project files not found")

    buffer = project_zip_bytes(project_dir)
    stem = Path(report.filename if report else job_id).stem
    filename = f"{stem or job_id}-scholarlint.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
                headers={"User-Agent": f"ScholarLint/5.3 (mailto:{settings.crossref_email})"},
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
    scholarly_headers = {"User-Agent": "ScholarLint/5.3 (mailto:integrity@check.org)"}
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={"query.title": title, "rows": 3},
                headers={"User-Agent": f"ScholarLint/5.3 (mailto:{settings.crossref_email})"},
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
                headers=scholarly_headers,
            )
            if resp.status_code == 200:
                candidates.extend(_candidate_from_s2(item) for item in resp.json().get("data", []))
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={"search": title, "per-page": 3},
                headers=scholarly_headers,
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
        target = safe_project_file(project_dir, file_path, allowed_suffixes=(".tex",))
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

def _new_batch_summary(limit: int) -> dict:
    """Create a machine-readable dry-run summary for AI batch suggestions."""
    return {
        "limit": limit,
        "total_error_issues": 0,
        "total_fixable": 0,
        "selected_for_generation": 0,
        "generated": 0,
        "skipped": defaultdict(int),
        "by_gate": defaultdict(lambda: {
            "total_error_issues": 0,
            "fixable": 0,
            "selected_for_generation": 0,
            "generated": 0,
            "skipped": 0,
        }),
    }


def _batch_summary_plain(summary: dict) -> dict:
    """Convert defaultdict-backed summary into JSON-stable plain dicts."""
    plain = dict(summary)
    plain["skipped"] = dict(summary["skipped"])
    plain["by_gate"] = {
        gate: dict(values)
        for gate, values in summary["by_gate"].items()
    }
    return plain


def _record_batch_skip(
    summary: dict,
    skipped: list[dict],
    gate_name: str,
    issue_index: int,
    issue,
    reason: str,
) -> None:
    summary["skipped"][reason] += 1
    summary["by_gate"][gate_name]["skipped"] += 1
    skipped.append({
        "gate_name": gate_name,
        "issue_index": issue_index,
        "reason": reason,
        "message": issue.message,
        "file": issue.file,
        "line": issue.line,
    })


def _collect_batch_fix_candidates(report: FullReport, project_dir: Path, limit: int = BATCH_FIX_LIMIT) -> tuple[list[dict], dict, list[dict]]:
    """Dry-run batch fix candidates without invoking the LLM.

    This keeps the safety policy testable: reference authenticity issues,
    dismissed issues, missing anchors, unreadable files, and over-limit items
    are reported explicitly instead of silently disappearing.
    """
    summary = _new_batch_summary(limit)
    skipped: list[dict] = []
    candidates: list[dict] = []
    dismissed = {
        (d.gate_name, d.issue_index)
        for d in report.dismissed_issues
    }

    for gate in report.gate_results:
        gate_name = gate.gate_name
        for issue_index, issue in enumerate(gate.issues):
            if issue.severity != Severity.ERROR:
                continue

            summary["total_error_issues"] += 1
            summary["by_gate"][gate_name]["total_error_issues"] += 1

            if (gate_name, issue_index) in dismissed:
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "dismissed")
                continue

            if gate_name == "reference_authenticity" or _is_reference_authenticity_issue(gate_name, issue.message):
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "reference_authenticity")
                continue

            if not issue.file:
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "missing_file")
                continue

            if not issue.line:
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "missing_line")
                continue

            try:
                target = safe_project_file(project_dir, issue.file, allowed_suffixes=BATCH_FIX_ALLOWED_SUFFIXES)
            except HTTPException:
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "unsupported_file")
                continue

            if not target.exists():
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "missing_file")
                continue

            lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
            start = max(0, issue.line - 4)
            end = min(len(lines), issue.line + 4)
            context = "\n".join(lines[start:end]).strip("\n")
            if not context.strip():
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "empty_context")
                continue

            summary["total_fixable"] += 1
            summary["by_gate"][gate_name]["fixable"] += 1
            candidate = {
                "gate_name": gate_name,
                "issue_index": issue_index,
                "message": issue.message,
                "file": issue.file,
                "line": issue.line,
                "suggestion": issue.suggestion or "",
                "context": context,
            }
            if len(candidates) < limit:
                summary["selected_for_generation"] += 1
                summary["by_gate"][gate_name]["selected_for_generation"] += 1
                candidates.append(candidate)
            else:
                _record_batch_skip(summary, skipped, gate_name, issue_index, issue, "over_limit")

    return candidates, _batch_summary_plain(summary), skipped


# ─── Reproducibility Checklist ───────────────────────────────

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
    tex_texts = []
    for f in project_dir.rglob("*.tex"):
        text = f.read_text(encoding="utf-8", errors="replace")
        tex_texts.append(text)
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
        "writing_style": analyze_writing_style(tex_texts),
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
    _job_locks.discard(job_id)
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
        _save_failed_report(job_id, filename, e, owner_metadata)
        logger.error(f" Job {job_id} failed: {redact(str(e))}")
    finally:
        _job_locks.discard(job_id)
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
            "status": "completed",
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
        _save_failed_report(job_id, filename, e, owner_metadata)
        logger.error(f" Recheck {job_id} failed: {redact(str(e))}")
    finally:
        _job_locks.discard(job_id)
