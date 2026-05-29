"""Job persistence layer (encrypted at rest).

Stores FullReport objects in data/jobs/{job_id}.enc — AES-encrypted (Fernet)
with the master key from the OS vault. Legacy plaintext {job_id}.json files
are still read for backward compatibility and migrated to .enc on next save.
If the encryption stack is unavailable, falls back to plaintext .json.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models import FullReport
from app import secrets_manager as sm

JOBS_DIR = settings.data_dir / "jobs"
JOB_RETENTION_DAYS = 7


def _ensure_dir():
    """Create the jobs directory if it doesn't exist."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _enc_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.enc"


def _json_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def save_report(job_id: str, report: FullReport) -> None:
    """Persist a report encrypted at rest (plaintext fallback if no crypto)."""
    _ensure_dir()
    payload = report.model_dump_json(indent=2).encode("utf-8")
    if sm.is_available():
        _enc_path(job_id).write_bytes(sm.encrypt_bytes(payload))
        # Remove any legacy plaintext copy now that it's encrypted.
        legacy = _json_path(job_id)
        if legacy.exists():
            legacy.unlink()
    else:
        _json_path(job_id).write_text(payload.decode("utf-8"), encoding="utf-8")


def _read_report_file(path: Path) -> FullReport | None:
    """Load+validate a report from a .enc (decrypt) or .json (plaintext) file."""
    try:
        if path.suffix == ".enc":
            raw = sm.decrypt_bytes(path.read_bytes()).decode("utf-8")
        else:
            raw = path.read_text(encoding="utf-8")
        return FullReport.model_validate_json(raw)
    except Exception:
        return None


def load_report(job_id: str) -> FullReport | None:
    """Load a report from disk (.enc first, then legacy .json). None if missing."""
    enc = _enc_path(job_id)
    if enc.exists():
        return _read_report_file(enc)
    legacy = _json_path(job_id)
    if legacy.exists():
        return _read_report_file(legacy)
    return None


def _iter_report_files():
    """Yield all report files (encrypted + legacy plaintext)."""
    yield from JOBS_DIR.glob("*.enc")
    yield from JOBS_DIR.glob("*.json")


def list_jobs(
    limit: int = 50,
    owner_type: str | None = None,
    owner_id: str | None = None,
    include_legacy: bool = True,
) -> list[dict]:
    """List recent jobs (id, filename, timestamp, score, passed, gate_count)."""
    _ensure_dir()
    jobs = []
    for f in _iter_report_files():
        report = _read_report_file(f)
        if not report:
            continue
        if owner_type and owner_id:
            metadata = report.metadata or {}
            report_owner_type = metadata.get("owner_type")
            report_owner_id = metadata.get("owner_id")
            if report_owner_type and report_owner_id:
                if report_owner_type != owner_type or str(report_owner_id) != str(owner_id):
                    continue
            elif not include_legacy:
                continue
        jobs.append({
            "job_id": report.job_id,
            "filename": report.filename,
            "timestamp": report.timestamp,
            "score": report.overall_score,
            "passed": report.overall_passed,
            "gates_passed": sum(1 for g in report.gate_results if g.passed),
            "gates_total": len(report.gate_results),
        })

    jobs.sort(key=lambda x: x["timestamp"], reverse=True)
    return jobs[:limit]


def delete_job(job_id: str) -> bool:
    """Delete a job's report file(s) and its uploaded files. True if anything deleted."""
    deleted = False
    for path in (_enc_path(job_id), _json_path(job_id)):
        if path.exists():
            path.unlink()
            deleted = True

    # Also remove uploaded project directory
    project_dir = settings.upload_dir / job_id
    if project_dir.exists() and project_dir.is_dir():
        shutil.rmtree(project_dir, ignore_errors=True)
        deleted = True

    return deleted


def cleanup_expired() -> int:
    """Remove jobs older than JOB_RETENTION_DAYS. Returns count of removed jobs."""
    _ensure_dir()
    now = datetime.now(timezone.utc)
    removed = 0

    for f in _iter_report_files():
        report = _read_report_file(f)
        if not report:
            continue
        try:
            ts = datetime.fromisoformat(report.timestamp)
        except Exception:
            continue
        if (now - ts).days > JOB_RETENTION_DAYS:
            delete_job(report.job_id)
            removed += 1

    return removed


def get_all_job_ids() -> list[str]:
    """Get all persisted job IDs (for startup recovery)."""
    _ensure_dir()
    return [f.stem for f in _iter_report_files()]
