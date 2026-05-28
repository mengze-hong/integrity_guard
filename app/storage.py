"""JSON-based job persistence layer.

Stores FullReport objects as JSON files in data/jobs/{job_id}.json.
Supports listing, loading, saving, and auto-cleanup of expired jobs.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models import FullReport

JOBS_DIR = settings.data_dir / "jobs"
JOB_RETENTION_DAYS = 7


def _ensure_dir():
    """Create the jobs directory if it doesn't exist."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def save_report(job_id: str, report: FullReport) -> None:
    """Persist a report to disk as JSON."""
    _ensure_dir()
    path = JOBS_DIR / f"{job_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def load_report(job_id: str) -> FullReport | None:
    """Load a report from disk. Returns None if not found."""
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return FullReport.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_jobs(limit: int = 50) -> list[dict]:
    """List recent jobs (id, filename, timestamp, score, passed, gate_count).

    Returns most recent first, up to `limit` entries.
    """
    _ensure_dir()
    jobs = []
    for f in JOBS_DIR.glob("*.json"):
        try:
            report = FullReport.model_validate_json(f.read_text(encoding="utf-8"))
            jobs.append({
                "job_id": report.job_id,
                "filename": report.filename,
                "timestamp": report.timestamp,
                "score": report.overall_score,
                "passed": report.overall_passed,
                "gates_passed": sum(1 for g in report.gate_results if g.passed),
                "gates_total": len(report.gate_results),
            })
        except Exception:
            continue

    # Sort by timestamp descending
    jobs.sort(key=lambda x: x["timestamp"], reverse=True)
    return jobs[:limit]


def delete_job(job_id: str) -> bool:
    """Delete a job's JSON file and its uploaded files. Returns True if deleted."""
    json_path = JOBS_DIR / f"{job_id}.json"
    deleted = False

    if json_path.exists():
        json_path.unlink()
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

    for f in JOBS_DIR.glob("*.json"):
        try:
            report = FullReport.model_validate_json(f.read_text(encoding="utf-8"))
            ts = datetime.fromisoformat(report.timestamp)
            age_days = (now - ts).days
            if age_days > JOB_RETENTION_DAYS:
                job_id = f.stem
                delete_job(job_id)
                removed += 1
        except Exception:
            continue

    return removed


def get_all_job_ids() -> list[str]:
    """Get all persisted job IDs (for startup recovery)."""
    _ensure_dir()
    return [f.stem for f in JOBS_DIR.glob("*.json")]
