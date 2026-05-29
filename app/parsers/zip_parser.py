"""ZIP file parser - extract and identify project structure from Overleaf zip."""

import zipfile
from pathlib import Path

from app.models import ParsedPaper


DANGEROUS_EXTENSIONS = (".exe", ".sh", ".bat", ".cmd", ".ps1", ".dll", ".so", ".bin", ".msi")


def _is_within(child: Path, parent: Path) -> bool:
    """True if resolved `child` is inside `parent` (path-component aware)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract zip file safely and return the project root directory.

    Validates all paths to prevent Zip Slip path traversal attacks and skips
    dangerous executable file types. Members are extracted one-by-one so the
    dangerous-file filter is actually enforced (a bulk extractall would ignore
    it). Handles the common case where the zip contains a single top-level
    folder.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_dir_resolved = dest_dir.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # Security: prevent path traversal (Zip Slip) — component-aware check
            target = dest_dir / member
            if not _is_within(target, dest_dir_resolved):
                raise ValueError(f"Unsafe path detected in zip: {member}")
            # Directory entry: create and continue
            if member.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            # Security: skip dangerous executable file types
            if any(member.lower().endswith(ext) for ext in DANGEROUS_EXTENSIONS):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())

    # Check if there's a single top-level directory
    items = list(dest_dir.iterdir())
    if len(items) == 1 and items[0].is_dir():
        return items[0]
    return dest_dir


def identify_project_structure(project_dir: Path) -> ParsedPaper:
    """Scan project directory and identify all relevant files.

    Returns a ParsedPaper with file lists populated (but not yet parsed).
    """
    all_files: list[Path] = []
    tex_files: list[Path] = []
    bib_files: list[Path] = []
    figure_files: list[Path] = []

    figure_extensions = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}

    for f in project_dir.rglob("*"):
        if f.is_file():
            all_files.append(f)
            suffix = f.suffix.lower()
            if suffix == ".tex":
                tex_files.append(f)
            elif suffix == ".bib":
                bib_files.append(f)
            elif suffix in figure_extensions:
                figure_files.append(f)

    paper = ParsedPaper(
        project_dir=project_dir,
        all_files=all_files,
        figure_files=figure_files,
    )

    # Set bib file path (use first found, or None)
    if bib_files:
        paper.bib_file_path = bib_files[0]

    return paper, tex_files, bib_files
