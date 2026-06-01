"""File-related API endpoints (split out of the legacy ``app.api.routes``).

Owns the four endpoints the editor uses to inspect and edit a job's project:

- ``GET  /api/files/{job_id}``                        — list editable files
- ``GET  /api/files/{job_id}/{file_path:path}``       — read one file
- ``PUT  /api/files/{job_id}/{file_path:path}``       — save one file
- ``GET  /api/download/{job_id}``                     — download project ZIP

External URLs are unchanged. Job state, ownership checks, and the file_store
helpers still live in ``app.api.routes`` and ``app.services.file_store``; this
module only re-exposes those four routes through its own ``APIRouter`` so the
god-module shrinks one slice at a time.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.api import routes as _legacy
from app.api.routes import (
    _get_report,
    _job_dirs,
    _require_job_access,
)
from app.services.file_store import (
    EDITABLE_EXTENSIONS,
    list_editable_files,
    project_zip_bytes,
    safe_project_file,
)
from app.services import edit_history
from app.secrets_manager import redact
from app.logging_config import logger


router = APIRouter()


@router.get("/files/{job_id}")
async def list_files(job_id: str, request: Request, response: Response):
    """List all editable files (.tex, .bib, .cls, .sty, ...) in the project."""
    await _require_job_access(job_id, request, response)
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

    # Defense-in-depth: confirm the resolved path stays inside the project.
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

    # Only allow editing known plain-text source files (blocks writing
    # binaries/executables while preserving the editor's normal use).
    if not any(file_path.lower().endswith(ext) for ext in EDITABLE_EXTENSIONS):
        raise HTTPException(status_code=403, detail="只能编辑文本源文件（.tex/.bib/.cls/.sty 等）")

    target = safe_project_file(project_dir, file_path, allowed_suffixes=EDITABLE_EXTENSIONS)

    # Capture the previous content (if any) before overwriting so the edit can
    # be tracked in history and reverted later.
    old_content: str | None = None
    if target.exists() and target.is_file():
        try:
            old_content = target.read_text(encoding="utf-8")
        except Exception:
            old_content = None

    body = await request.body()
    content = body.decode("utf-8")
    target.write_text(content, encoding="utf-8")

    # Record the change in the per-job edit history (best-effort: a history
    # failure must never break saving the user's work).
    try:
        edit_history.record_edit(job_id, file_path, content, old_content)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"edit history record failed for {job_id}: {redact(str(exc))}")

    return {"status": "saved", "path": file_path, "size": len(content)}


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


# Functions remain importable by name (FastAPI decorators return the original
# function), so legacy callers like `from app.api.file_routes import save_file`
# continue to work alongside the router. The legacy ``app.api.routes`` module
# is touched here to keep its module-level state alive in test harnesses that
# still import it directly.
_ = _legacy
