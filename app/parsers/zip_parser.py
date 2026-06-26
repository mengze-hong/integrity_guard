"""ZIP file parser - extract and identify project structure from Overleaf zip."""

import shutil
import stat
from pathlib import PurePosixPath
import zipfile
from pathlib import Path

from app.models import ParsedPaper


DANGEROUS_EXTENSIONS = (
    ".exe", ".sh", ".bat", ".cmd", ".ps1", ".dll", ".so", ".bin", ".msi",
    ".jar", ".vbs", ".js", ".scr", ".com", ".docm", ".xlsm", ".pptm",
)
MAX_ZIP_MEMBERS = 2_000
MAX_UNCOMPRESSED_TOTAL = 200 * 1024 * 1024
MAX_UNCOMPRESSED_FILE = 50 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_PATH_DEPTH = 20


def _is_within(child: Path, parent: Path) -> bool:
    """True if resolved `child` is inside `parent` (path-component aware)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _normalized_member_name(name: str) -> str:
    """Normalize a ZIP member name and reject absolute/traversal paths."""
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"Unsafe path detected in zip: {name}")
    if len(path.parts) > MAX_PATH_DEPTH:
        raise ValueError(f"ZIP path too deep: {name}")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """Detect Unix symlink entries encoded in external attributes."""
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK


def _validate_zip_members(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    """Validate ZIP metadata before extraction to block zip bombs early."""
    infos = zf.infolist()
    if len(infos) > MAX_ZIP_MEMBERS:
        raise ValueError(f"ZIP contains too many files ({len(infos)} > {MAX_ZIP_MEMBERS})")

    total_uncompressed = 0
    seen_names: set[str] = set()
    validated = []
    for info in infos:
        member_name = _normalized_member_name(info.filename)
        member_key = member_name.casefold()
        if member_key in seen_names:
            raise ValueError(f"Duplicate ZIP member after normalization: {info.filename}")
        seen_names.add(member_key)

        if _is_symlink(info):
            raise ValueError(f"Symlink entries are not allowed in zip: {info.filename}")

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_UNCOMPRESSED_TOTAL:
            raise ValueError("ZIP uncompressed size exceeds limit")
        if info.file_size > MAX_UNCOMPRESSED_FILE:
            raise ValueError(f"ZIP member too large: {info.filename}")
        if info.compress_size and info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
            raise ValueError(f"Suspicious compression ratio in zip member: {info.filename}")

        validated.append((info, member_name))

    return validated


def extract_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract zip file safely and return the project root directory.

    Validates all paths to prevent Zip Slip path traversal attacks and skips
    dangerous executable file types. Members are extracted one-by-one so the
    dangerous-file filter is actually enforced (a bulk extractall would ignore
    it). Handles the common case where the zip contains a single top-level
    folder.
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_dir_resolved = dest_dir.resolve()

        with zipfile.ZipFile(zip_path, "r") as zf:
            validated_members = _validate_zip_members(zf)
            for info, member in validated_members:
                target = dest_dir / member
                if not _is_within(target, dest_dir_resolved):
                    raise ValueError(f"Unsafe path detected in zip: {info.filename}")
                # Directory entry: create and continue
                if info.is_dir() or member.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                # Security: skip dangerous executable file types
                if any(member.lower().endswith(ext) for ext in DANGEROUS_EXTENSIONS):
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)

        # Check if there's a single top-level directory
        items = list(dest_dir.iterdir())
        if len(items) == 1 and items[0].is_dir():
            return items[0]
        return dest_dir
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise


def identify_project_structure(project_dir: Path) -> ParsedPaper:
    """Scan project directory and identify all relevant files.

    Returns a ParsedPaper with file lists populated (but not yet parsed).
    """
    all_files: list[Path] = []
    tex_files: list[Path] = []
    bib_files: list[Path] = []
    bbl_files: list[Path] = []
    figure_files: list[Path] = []

    figure_extensions = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}

    bbl_files: list[Path] = []

    for f in project_dir.rglob("*"):
        if f.is_file():
            all_files.append(f)
            suffix = f.suffix.lower()
            if suffix == ".tex":
                tex_files.append(f)
            elif suffix == ".bib":
                bib_files.append(f)
            elif suffix == ".bbl":
                bbl_files.append(f)
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

    return paper, tex_files, bib_files, bbl_files
