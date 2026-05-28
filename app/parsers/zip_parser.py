"""ZIP file parser - extract and identify project structure from Overleaf zip."""

import zipfile
from pathlib import Path

from app.models import ParsedPaper


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract zip file and return the project root directory.

    Handles the common case where zip contains a single top-level folder.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

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
