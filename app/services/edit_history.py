"""Per-job edit history (encrypted at rest).

Records every editor save so a user can review what changed, when, and revert
to a previous version of a file. History is stored next to job reports in
``data/jobs/{job_id}.history.enc`` and encrypted with the same Fernet stack as
reports (plaintext ``.history.json`` fallback when crypto is unavailable),
because file contents are sensitive paper data.

The history is intentionally bounded: at most ``MAX_ENTRIES`` recent entries
are kept, and very large file snapshots store only a summary (no full content)
so the history cannot grow without limit. Entries that kept their snapshot can
be reverted; entries without a stored snapshot are review-only.
"""

from __future__ import annotations

import json
import secrets as _secrets
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app import secrets_manager as sm

JOBS_DIR = settings.data_dir / "jobs"

# Keep history bounded so it cannot grow without limit.
MAX_ENTRIES = 100
# Snapshots larger than this are summarized (not stored), so a single huge file
# cannot blow up the history. Such entries are review-only (cannot revert).
MAX_SNAPSHOT_CHARS = 512 * 1024


def _ensure_dir() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _enc_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.history.enc"


def _json_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.history.json"


def _load_raw(job_id: str) -> list[dict]:
    """Load the raw entry list for a job (newest entries appended last)."""
    enc = _enc_path(job_id)
    legacy = _json_path(job_id)
    try:
        if enc.exists():
            raw = sm.decrypt_bytes(enc.read_bytes()).decode("utf-8")
        elif legacy.exists():
            raw = legacy.read_text(encoding="utf-8")
        else:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _save_raw(job_id: str, entries: list[dict]) -> None:
    _ensure_dir()
    payload = json.dumps(entries, ensure_ascii=False).encode("utf-8")
    if sm.is_available():
        _enc_path(job_id).write_bytes(sm.encrypt_bytes(payload))
        legacy = _json_path(job_id)
        if legacy.exists():
            legacy.unlink()
    else:
        _json_path(job_id).write_text(payload.decode("utf-8"), encoding="utf-8")


def _line_delta(old_content: str | None, new_content: str) -> dict:
    """Summarize the size of a change for display without a full diff."""
    new_lines = new_content.count("\n") + 1 if new_content else 0
    if old_content is None:
        return {"old_lines": 0, "new_lines": new_lines, "line_delta": new_lines}
    old_lines = old_content.count("\n") + 1 if old_content else 0
    return {
        "old_lines": old_lines,
        "new_lines": new_lines,
        "line_delta": new_lines - old_lines,
    }


def record_edit(
    job_id: str,
    file_path: str,
    new_content: str,
    old_content: str | None,
) -> dict | None:
    """Record one save. Returns the stored entry, or None if it was a no-op.

    No history entry is created when content is unchanged. Large snapshots are
    summarized (content omitted) so they remain review-only.
    """
    if old_content is not None and old_content == new_content:
        return None

    delta = _line_delta(old_content, new_content)
    too_large = (
        len(new_content) > MAX_SNAPSHOT_CHARS
        or (old_content is not None and len(old_content) > MAX_SNAPSHOT_CHARS)
    )
    entry = {
        "id": _secrets.token_hex(8),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "file_path": file_path,
        "old_lines": delta["old_lines"],
        "new_lines": delta["new_lines"],
        "line_delta": delta["line_delta"],
        "is_creation": old_content is None,
        "revertable": not too_large,
    }
    if not too_large:
        entry["old_content"] = old_content
        entry["new_content"] = new_content

    entries = _load_raw(job_id)
    entries.append(entry)
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    _save_raw(job_id, entries)
    return entry


def _public_entry(entry: dict) -> dict:
    """Strip stored file contents; keep only metadata for list responses."""
    return {
        "id": entry.get("id"),
        "timestamp": entry.get("timestamp"),
        "file_path": entry.get("file_path"),
        "old_lines": entry.get("old_lines", 0),
        "new_lines": entry.get("new_lines", 0),
        "line_delta": entry.get("line_delta", 0),
        "is_creation": entry.get("is_creation", False),
        "revertable": entry.get("revertable", False) and "new_content" in entry,
    }


def list_history(job_id: str, file_path: str | None = None) -> list[dict]:
    """Return history metadata (newest first), optionally filtered by file."""
    entries = _load_raw(job_id)
    if file_path:
        entries = [e for e in entries if e.get("file_path") == file_path]
    return [_public_entry(e) for e in reversed(entries)]


def get_entry(job_id: str, entry_id: str) -> dict | None:
    """Return a full entry (including stored contents) by id, or None."""
    for entry in _load_raw(job_id):
        if entry.get("id") == entry_id:
            return entry
    return None


def delete_history(job_id: str) -> bool:
    """Delete a job's history file(s). True if anything was removed."""
    removed = False
    for path in (_enc_path(job_id), _json_path(job_id)):
        if path.exists():
            path.unlink()
            removed = True
    return removed
