"""Core API routes for ScholarLint.

After three rounds of structural splits (v5.3.94 file_routes, v5.3.95
tool_routes, v5.3.96 checklist_routes) this module owns only the
endpoints that touch the central ``FullReport`` lifecycle and the
shared infrastructure that every other router still imports from here:

Endpoints (in source order):
    Upload & status
        POST   /api/upload                        upload + extract + run gates
        GET    /api/status/{job_id}               polling for the upload job
        GET    /api/report/{job_id}               full report JSON
    Edit history (per-job timeline + revert)
        GET    /api/history-edits/{job_id}
        GET    /api/history-edits/{job_id}/{entry_id}
        POST   /api/history-edits/{job_id}/{entry_id}/revert
    Re-check / dismiss / export
        POST   /api/recheck/{job_id}              re-run gates after edits
        POST   /api/dismiss/{job_id}              human-in-the-loop suppression
        GET    /api/export/{job_id}               branded markdown report
    Job-level browsing
        GET    /api/history                       recent jobs (per owner)
        GET    /api/compare/{job_id}              diff vs previous run
        GET    /api/score-trend/{job_id}          score history for a job lineage
        GET    /api/analysis/{job_id}             style analysis snapshot
        DELETE /api/job/{job_id}                  remove job + history
    AI batch fixes
        POST   /api/ai-batch-suggest-fix/{job_id}
        ...   (rest live in the AI Batch section)

Shared infrastructure exported from this module:
    Process-level state — ``_jobs``, ``_job_status``, ``_job_dirs``,
        ``_job_progress``, ``_job_owners``, ``_job_locks``.
        Tests reset these via ``tests.conftest.clear_route_state``.
    Permission/session helpers — ``_get_request_owner``,
        ``_owner_metadata_allows``, ``_require_job_access``,
        ``_secure_session_cookie``, ``_set_session_cookie_if_needed``.
    Persistence helpers — ``_get_report``.
    Rate-limit helpers — ``_rate_limit``, ``_check_rate_limit``,
        ``_llm_calls_by_ip``, ``_llm_calls_global``, ``_llm_usage_guard``.
    LLM gateway helper — ``_llm_chat_post`` (used by ``ai_routes``,
        ``checklist_routes``, and the AI-batch endpoints below).
    AI-batch helper — ``_collect_batch_fix_candidates``.

The split sibling routers (``file_routes``, ``tool_routes``,
``checklist_routes``, ``ai_routes``) intentionally import these helpers
from here to keep a single source of truth for permission and state
management. A future M4 may extract them into ``app/services/permissions.py``
to break the import direction; until then, prefer adding new shared
helpers here rather than copying them.

Security/operational invariants worth keeping:
    * ``_require_job_access`` returns the report; per-job gating uses
      ``_owner_metadata_allows`` which denies legacy no-owner reports
      in production (see SECURE-S1 / v5.3.91).
    * Reference-authenticity issues never invoke the LLM (see
      ``app.services.ai_guardrails``); the AI-batch path filters them
      out via ``_is_reference_authenticity_issue``.
    * Logged exception strings go through ``app.secrets_manager.redact``
      so JWTs / Bearer tokens / PEM blocks do not leak into logs.
"""

import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

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
from app.services.ai_guardrails import (
    ai_fix_provenance as _ai_fix_provenance,
    is_reference_authenticity_issue as _is_reference_authenticity_issue,
    not_fixable_reference_payload as _not_fixable_reference_payload,
)
from app.services.file_store import (
    EDITABLE_EXTENSIONS,
    safe_project_file,
)
from app.services.dimension_scores import build_dimension_scores
from app.services.style_analysis import analyze_writing_style
from app.services import edit_history
from app.services.permissions import (  # noqa: F401  (re-exported for back-compat)
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_MAX_AGE,
    request_share_token as _request_share_token,
    secure_session_cookie as _secure_session_cookie,
    set_session_cookie_if_needed as _set_session_cookie_if_needed,
    new_share_token as _new_share_token,
    owner_metadata as _owner_metadata,
    extract_owner_metadata as _extract_owner_metadata,
    request_uses_valid_share_token as _request_uses_valid_share_token,
    owner_metadata_allows as _owner_metadata_allows_impl,
    can_access_report as _can_access_report_impl,
)
from app import storage
from app.logging_config import logger

router = APIRouter()

# Names whose call sites span multiple modules (sibling routers, tests).
# Anything in __all__ is part of the implicit public-within-package API
# of this module and should not be renamed without a sweep.
__all__ = [
    "_ai_fix_provenance",
    "_collect_batch_fix_candidates",
    "_is_reference_authenticity_issue",
    "_not_fixable_reference_payload",
    "router",
]

# ── Process-level state ──────────────────────────────────────
# Authoritative persistence is on disk (see ``app.storage``). These
# dicts are caches and ephemeral coordination flags; tests reset them
# via ``tests.conftest.clear_route_state`` so cross-test contamination
# is impossible.
_jobs: dict[str, FullReport] = {}
_job_status: dict[str, str] = {}
_job_dirs: dict[str, Path] = {}  # job_id → extracted project directory
_job_progress: dict[str, list[str]] = {}  # job_id → list of completed gate names
_job_owners: dict[str, dict] = {}  # job_id → owner/share metadata during a run
_job_locks: set[str] = set()  # job_ids currently running checks/rechecks

# AI-batch caps. The LLM is allowed at most BATCH_FIX_LIMIT suggestions
# per request to bound cost; only text-source files are eligible because
# binary edits cannot be safely diffed/applied.
BATCH_FIX_LIMIT = 5
BATCH_FIX_ALLOWED_SUFFIXES = (".tex", ".bib")

# Anonymous-session cookie. Stateless helpers and the cookie name/TTL
# live in ``app.services.permissions`` (see M4 / v5.3.98). The names
# are re-exported above next to the rest of the imports so existing
# call sites in this module and any legacy importers keep working
# unchanged.


# ── Owner / access helpers ───────────────────────────────────
# The stateless share-token / cookie / owner-metadata helpers come from
# ``app.services.permissions`` (imported above). The two helpers below
# stay here because they bind to ``_get_request_owner``, which itself
# must live in this module to avoid a permissions ↔ dependencies
# circular import.


async def _get_request_owner(
    request: Request,
    response: Response | None = None,
    current_user=None,
) -> dict:
    """Resolve the request's logical owner (user or anonymous session).

    The result drives both ``_owner_metadata_allows`` (per-request access
    decisions) and the ownership metadata stamped onto new jobs at upload
    time.

    Resolution order:
        1. The injected ``current_user`` (callers that already loaded one).
        2. ``app.dependencies.get_current_user_optional`` — recognises
           cookie JWT, Bearer JWT, and ``sl_api_`` API tokens (S2/v5.3.92).
        3. Anonymous: an ``sl_session`` cookie. If absent, a fresh random
           id is generated and written back to ``response`` (when given).

    Stays in ``routes.py`` (not extracted to ``app.services.permissions``)
    because it imports ``app.dependencies`` which would otherwise create a
    permissions ↔ dependencies circular import.

    Returns a dict with ``owner_type`` ("user" | "session"), ``owner_id``,
    and (for sessions) the raw ``session_id`` so callers can stamp it
    on share-link metadata.
    """
    if current_user is None:
        from app.dependencies import get_current_user_optional

        current_user = await get_current_user_optional(request)

    if current_user:
        return {"owner_type": "user", "owner_id": str(current_user.id)}

    session_id = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if not session_id:
        session_id = secrets.token_urlsafe(32)
        _set_session_cookie_if_needed(response, session_id, request)
    return {"owner_type": "session", "owner_id": session_id, "session_id": session_id}


async def _owner_metadata_allows(
    metadata: dict,
    request: Request,
    response: Response | None = None,
    *,
    write: bool = False,
    allow_share: bool = True,
) -> bool:
    """Bind ``permissions.owner_metadata_allows`` to this module's
    ``_get_request_owner`` so existing call sites do not need to thread
    the loader through. Pure delegation; see the underlying helper for
    the access-decision tree.
    """
    return await _owner_metadata_allows_impl(
        metadata,
        request,
        response,
        request_owner_loader=_get_request_owner,
        write=write,
        allow_share=allow_share,
    )


async def _can_access_report(
    report: FullReport,
    request: Request,
    response: Response | None = None,
    *,
    mode: str = "read",
    allow_share: bool = True,
) -> bool:
    """Bind ``permissions.can_access_report`` to this module's owner loader."""
    return await _can_access_report_impl(
        report,
        request,
        response,
        request_owner_loader=_get_request_owner,
        mode=mode,
        allow_share=allow_share,
    )


async def _is_owner(
    report: FullReport,
    request: Request,
    response: Response | None = None,
) -> bool:
    """True when the request is from the report's actual owner.

    Share-token viewers return ``False`` here even though they pass
    ``_can_access_report`` — used to decide whether to send the full
    payload or the share-redacted variant.
    """
    metadata = _extract_owner_metadata(report)
    owner_type = metadata.get("owner_type")
    owner_id = metadata.get("owner_id")
    if not owner_type or not owner_id:
        return False
    request_owner = await _get_request_owner(request, response)
    return (
        request_owner["owner_type"] == owner_type
        and request_owner["owner_id"] == str(owner_id)
    )


# Fields stripped from the report payload when a share-token viewer
# (mentor / supervisor with the read-only link) calls ``/api/report``.
# Owners always get the unredacted payload.
_SHARE_REPORT_REDACTED_METADATA_KEYS = (
    "owner_type",
    "owner_id",
    "session_id",
    "share_token",
)


def _share_readonly_report_payload(payload: dict) -> dict:
    """Strip owner-only fields from a serialized FullReport.

    What share viewers should still see: gate results, scores,
    dismiss-list **counts** (so their justifications were considered),
    and the high-level paper metadata (filename, timestamps, status).

    What gets redacted:

    * ``project_dir`` — server-side filesystem path.
    * ``metadata.owner_type`` / ``owner_id`` / ``session_id`` — caller
      identifiers; share users only need to know whose paper they
      review, not the internal id.
    * ``metadata.share_token`` — never echo a share token back over the
      wire (defence in depth: even though the viewer sent it, the
      response could be cached / logged in front of TLS).
    * ``dismissed_issues`` — student-authored justifications are
      author-internal; share viewers see the dismiss summary inside
      the markdown export instead.

    The function does not mutate the input.
    """
    if not isinstance(payload, dict):
        return payload
    redacted = dict(payload)
    redacted["project_dir"] = ""
    redacted["dismissed_issues"] = []
    metadata = dict(redacted.get("metadata") or {})
    for key in _SHARE_REPORT_REDACTED_METADATA_KEYS:
        metadata.pop(key, None)
    redacted["metadata"] = metadata
    return redacted


async def _require_job_access(
    job_id: str,
    request: Request,
    response: Response | None = None,
    *,
    write: bool = False,
    allow_share: bool = True,
) -> FullReport | None:
    """Require access to ``job_id``; raise 403/404 otherwise.

    Returns the report when one is on disk (loaded into the cache as a
    side-effect of ``_get_report``). Returns ``None`` when the job is
    still running and only ``_job_owners`` / ``_job_status`` knows about
    it — callers that need the report should re-check after the run
    finishes.

    Behaviour:
        * No record in any cache or status table → 404.
        * Report exists but caller is not the owner / has no valid
          share token → 403.
        * Report exists and access checks pass → return the report.
        * Job still pending (status only) but caller is the owner →
          return ``None``.
    """
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
    """Fetch a report from the in-memory cache, falling back to disk.

    On a disk hit, also rehydrates the related caches so subsequent
    requests in the same process do not re-read disk:

    * ``_jobs[job_id]`` ← the report itself
    * ``_job_status[job_id]`` ← persisted status (or ``"completed"``)
    * ``_job_dirs[job_id]`` ← extracted project directory if it still
      exists (gone after manual cleanup or container restart on
      ephemeral volumes — the caller has to handle ``None``)
    * ``_job_owners[job_id]`` ← ownership metadata (so access checks
      survive a process restart without reloading the full report)

    Returns ``None`` when nothing exists on disk; never raises.
    """
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


def _llm_creds(request: Request) -> dict | None:
    """Extract BYOK credentials from request headers.

    Frontend sends the user's own OpenAI-compatible key/base_url/model via
    X-LLM-Key / X-LLM-Base-URL / X-LLM-Model. Returns None when key or
    base_url is missing (callers then fall back to server settings).
    """
    key = (request.headers.get("X-LLM-Key") or "").strip()
    base = (request.headers.get("X-LLM-Base-URL") or "").strip()
    model = (request.headers.get("X-LLM-Model") or "").strip()
    if not key or not base:
        return None
    return {"api_key": key, "base_url": base, "model": model or settings.llm_model}


def _llm_usage_guard(request: Request):
    """Enforce per-IP rate limit + global hourly cap on LLM-backed endpoints.

    Raises HTTP 429 when a limit is exceeded. Protects the internal LLM from
    abuse (important when the app is exposed via a public tunnel).

    BYOK: when the request carries the user's own key, skip the global quota
    (they pay their own LLM) but keep a per-IP rate limit as an abuse guard.
    """
    now = time.time()
    ip = request.client.host if request.client else "unknown"
    byok = _llm_creds(request) is not None
    global _llm_calls_global
    _llm_calls_global[:] = [t for t in _llm_calls_global if now - t < 3600]
    _llm_calls_by_ip[ip] = [t for t in _llm_calls_by_ip[ip] if now - t < LLM_RATE_WINDOW]

    if not byok and len(_llm_calls_global) >= LLM_GLOBAL_HOURLY_CAP:
        raise HTTPException(status_code=429, detail="AI service hourly global limit reached — please try again later")
    if len(_llm_calls_by_ip[ip]) >= LLM_RATE_PER_IP:
        raise HTTPException(status_code=429, detail="Too many AI requests — please slow down")

    _llm_calls_by_ip[ip].append(now)
    if not byok:
        _llm_calls_global.append(now)
    # Bound memory: drop empty/stale IP buckets occasionally
    if len(_llm_calls_by_ip) > 5000:
        for k in [k for k, v in _llm_calls_by_ip.items() if not v]:
            del _llm_calls_by_ip[k]


# ─── Shared LLM call helper ───────────────────────────────────
# Reasoning models (e.g. gpt-5.5) reject a non-default `temperature`; this
# helper transparently retries without it so all AI features keep working
# regardless of which model `LLM_MODEL` points to.

async def _llm_chat_post(client, messages, max_tokens, temperature=None, creds=None):
    """POST a chat completion to an OpenAI-compatible proxy with fallback.

    ``creds`` (BYOK): {api_key, base_url, model} from the user's request.
    Falls back to server ``settings`` when not provided.
    """
    base_url = (creds or {}).get("base_url") or settings.llm_base_url
    api_key = (creds or {}).get("api_key") or settings.llm_api_key
    model = (creds or {}).get("model") or settings.llm_model
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
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
    """Upload a LaTeX project ZIP and kick off integrity checks.

    The endpoint is the entry point of the entire pipeline:

    1. Validate the upload (size cap, ZIP magic bytes, rate-limit per IP).
    2. Extract the archive into ``settings.upload_dir`` and stamp the
       owner / share-token metadata onto the new job.
    3. For logged-in users, deduct one check credit before queueing the
       background gates (so a failed billing attempt cannot start work).
    4. Schedule the gate runner as a background task and return the
       ``job_id`` so the client can poll ``/api/status/{job_id}``.

    Failures during validation or billing return synchronously with a
    descriptive error; failures inside the background task are persisted
    via ``_save_failed_report`` so polling still works after a restart.
    """
    from app.dependencies import get_current_user_optional
    from app.credits import deduct_check_credit, InsufficientCredits
    from app.database import SessionLocal
    from app.auth import refresh_free_tier_monthly_credits
    from app.models_db import User

    # Check auth + credits
    user = await get_current_user_optional(request)
    if user:
        db = SessionLocal()
        try:
            user = refresh_free_tier_monthly_credits(
                db,
                db.query(User).filter(User.id == user.id).first(),
            )
            deduct_check_credit(db, user.id, settings.credits_upload, "论文质检")
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
    llm_creds = _llm_creds(request)  # BYOK: user's own key for NCG (may be None)
    background_tasks.add_task(_run_checks, job_id, upload_path, extract_dir, file.filename, owner_metadata, llm_creds)

    return {"job_id": job_id, "status": "processing", "share_token": owner_metadata["share_token"]}


@router.get("/status/{job_id}")
async def get_status(job_id: str, request: Request, response: Response):
    """Polling endpoint used while ``/api/upload`` is still running.

    Returns the current ``status`` (``processing`` / ``completed`` /
    ``failed``) and the list of gate names finished so far so the UI
    can show a progress bar.
    """
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
    """Return the full report JSON, including dimension scores.

    Returns ``202 Still processing`` if the gates have not finished yet
    so the UI can keep polling. Dimension scores are computed on the fly
    so they always reflect the latest gate results without an extra
    persistence step.

    Share-readonly viewers (i.e. callers presenting a valid share token
    rather than being the owner) get a redacted payload that omits
    ownership identifiers, the share token itself, the on-disk
    ``project_dir``, and the dismiss audit trail (which includes
    student-written justifications and is owner-only). See
    ``_share_readonly_report_payload`` for the exact field policy.
    """
    report = await _require_job_access(job_id, request, response)
    if not report:
        status = _job_status.get(job_id, "not_found")
        if status == "processing":
            raise HTTPException(status_code=202, detail="Still processing")
        raise HTTPException(status_code=404, detail="Report not found")
    payload = report.model_dump()
    payload["dimension_scores"] = build_dimension_scores(report)
    if _request_uses_valid_share_token(report, request) and not await _is_owner(report, request, response):
        payload = _share_readonly_report_payload(payload)
    return payload


# ─── File CRUD endpoints moved to app.api.file_routes ─────────


# ─── Edit history (track changes, review timeline, revert) ────

@router.get("/history-edits/{job_id}")
async def list_edit_history(job_id: str, request: Request, response: Response, file: str | None = None):
    """List the edit history for a job (newest first), optionally one file.

    Read access is enough to view history (owner or valid share token).
    """
    await _require_job_access(job_id, request, response)
    return {"job_id": job_id, "file": file, "entries": edit_history.list_history(job_id, file)}


@router.get("/history-edits/{job_id}/{entry_id}")
async def get_edit_history_entry(job_id: str, entry_id: str, request: Request, response: Response):
    """Return one history entry with before/after content for a diff view."""
    await _require_job_access(job_id, request, response)
    entry = edit_history.get_entry(job_id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    return {
        "id": entry.get("id"),
        "timestamp": entry.get("timestamp"),
        "file_path": entry.get("file_path"),
        "old_lines": entry.get("old_lines", 0),
        "new_lines": entry.get("new_lines", 0),
        "line_delta": entry.get("line_delta", 0),
        "is_creation": entry.get("is_creation", False),
        "revertable": entry.get("revertable", False) and "new_content" in entry,
        "old_content": entry.get("old_content"),
        "new_content": entry.get("new_content"),
    }


@router.post("/history-edits/{job_id}/{entry_id}/revert")
async def revert_edit_history_entry(job_id: str, entry_id: str, request: Request, response: Response):
    """Revert a file to the 'before' content captured in a history entry.

    Requires write access (share-token readers are rejected). The revert is
    itself recorded as a new history entry, so it can also be undone.
    """
    await _require_job_access(job_id, request, response, write=True)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    entry = edit_history.get_entry(job_id, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    if "old_content" not in entry or entry.get("old_content") is None:
        raise HTTPException(status_code=400, detail="该记录无法回退（无可恢复的历史内容）")

    file_path = entry["file_path"]
    if not any(file_path.lower().endswith(ext) for ext in EDITABLE_EXTENSIONS):
        raise HTTPException(status_code=403, detail="只能回退文本源文件")

    target = safe_project_file(project_dir, file_path, allowed_suffixes=EDITABLE_EXTENSIONS)
    restore_content = entry["old_content"]

    current_content: str | None = None
    if target.exists() and target.is_file():
        try:
            current_content = target.read_text(encoding="utf-8")
        except Exception:
            current_content = None

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(restore_content, encoding="utf-8")

    try:
        edit_history.record_edit(job_id, file_path, restore_content, current_content)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"edit history revert record failed for {job_id}: {redact(str(exc))}")

    return {
        "status": "reverted",
        "file_path": file_path,
        "content": restore_content,
        "size": len(restore_content),
    }


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
    llm_creds = _llm_creds(request)  # BYOK for NCG on recheck
    background_tasks.add_task(_run_checks_from_dir, job_id, project_dir, filename, old_dismissed, owner_metadata, llm_creds)

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


# Project ZIP download moved to app.api.file_routes.


# ─── Bib Cleaning Tools ──────────────────────────────────────

# Editor-side tool endpoints (bib clean, fetch-bib, reference candidates,
# tidy-up, format normalization) live in app.api.tool_routes.


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
# venue-checklist endpoint moved to app.api.checklist_routes.


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
            include_legacy=True,
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
    # Best-effort: also remove the per-job edit history.
    try:
        edit_history.delete_history(job_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"edit history delete failed for {job_id}: {redact(str(exc))}")
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


# ─── Internal helpers ─────────────────────────────────────────

async def _run_checks(job_id: str, zip_path: Path, extract_dir: Path, filename: str, owner_metadata: dict, llm_creds: dict | None = None):
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

        await _run_checks_from_dir(job_id, project_dir, filename, [], owner_metadata, llm_creds)
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
    llm_creds: dict | None = None,
):
    """Run checks from an already-extracted directory."""
    try:
        from app.parsers.zip_parser import identify_project_structure
        from app.parsers.bbl_parser import parse_all_bbl_files, extract_inline_bib_entries

        paper, tex_paths, bib_paths, bbl_paths = identify_project_structure(project_dir)
        paper.tex_files = parse_all_tex_files(tex_paths)
        paper.bib_entries = parse_all_bib_files(bib_paths)
        if not paper.bib_entries and bbl_paths:
            paper.bib_entries = parse_all_bbl_files(bbl_paths)
        if not paper.bib_entries:
            paper.bib_entries = extract_inline_bib_entries(paper.tex_files)

        # BYOK: hand the user's own LLM creds to the gates (NCG reads this).
        paper.llm_config = llm_creds

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
