"""Safe file operations for uploaded LaTeX projects."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException

EDITABLE_EXTENSIONS = (".tex", ".bib", ".cls", ".sty", ".bst", ".txt", ".md")


def safe_project_file(
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


def list_editable_files(project_dir: Path) -> list[dict]:
    """Return editable project source files for the browser file tree."""
    files = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EDITABLE_EXTENSIONS:
            continue
        rel = path.relative_to(project_dir)
        suffix = path.suffix.lower().lstrip(".")
        files.append({
            "path": rel.as_posix(),
            "name": path.name,
            "type": suffix or "text",
            "size": path.stat().st_size,
        })
    return files


def project_zip_bytes(project_dir: Path) -> BytesIO:
    """Create an in-memory ZIP archive from the current project directory."""
    buffer = BytesIO()
    root = project_dir.resolve()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(project_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root)
            except ValueError:
                continue
            zf.write(path, path.relative_to(project_dir).as_posix())
    buffer.seek(0)
    return buffer
