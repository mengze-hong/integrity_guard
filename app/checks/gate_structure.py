"""Gate 1: Project Structure Integrity.

Verifies that the uploaded project has a valid structure:
1. At least one .tex and one .bib file exist
2. Main .tex can be identified (has \\documentclass + \\begin{document})
3. All \\input{}/\\include{} referenced files exist
4. All \\includegraphics{} referenced images exist
5. All \\bibliography{} referenced .bib files exist
6. No duplicate \\label{} definitions
7. No orphan \\ref{} references
8. No duplicate (copy-pasted) images
"""

import hashlib
import re
import struct
from collections import Counter
from pathlib import Path

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity

_BIBLIOGRAPHY_PATTERN = re.compile(r"\\bibliography\{([^}]+)\}")
_ADDBIBRESOURCE_PATTERN = re.compile(r"\\addbibresource(?:\[[^\]]*\])?\{([^}]+)\}")
_GRAPHICSPATH_PATTERN = re.compile(r"\\graphicspath\s*\{((?:\{[^{}]+\}\s*)+)\}", re.DOTALL)
_LOW_RASTER_MIN_DIMENSION = 600
_LARGE_IMAGE_BYTES = 5 * 1024 * 1024


def _graphicspath_dirs(raw_text: str, base_dir: Path) -> list[Path]:
    """Extract \\graphicspath directories relative to the current tex file."""
    dirs: list[Path] = []
    for match in _GRAPHICSPATH_PATTERN.finditer(raw_text):
        for item in re.findall(r"\{([^{}]+)\}", match.group(1)):
            dirs.append(base_dir / item)
    return dirs


def _raster_dimensions(path: Path) -> tuple[int, int] | None:
    """Read PNG/JPEG dimensions without loading the whole image into memory.

    Only the file header (PNG) or the bytes up to the SOF marker (JPEG) are
    read, so large figures do not get fully read just to learn their size.
    """
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg"}:
        return None

    try:
        with path.open("rb") as fh:
            if suffix == ".png":
                head = fh.read(24)
                if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                    return struct.unpack(">II", head[16:24])
                return None

            # JPEG: scan segment headers, reading only each segment's length
            # bytes (and the few SOF payload bytes) instead of the whole file.
            if fh.read(2) != b"\xff\xd8":
                return None
            while True:
                byte = fh.read(1)
                if not byte:
                    return None
                if byte != b"\xff":
                    continue
                marker = fh.read(1)
                if not marker:
                    return None
                marker_val = marker[0]
                if marker_val in {0xD8, 0xD9}:
                    continue
                length_bytes = fh.read(2)
                if len(length_bytes) < 2:
                    return None
                segment_len = int.from_bytes(length_bytes, "big")
                if segment_len < 2:
                    return None
                if marker_val in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    sof = fh.read(5)
                    if len(sof) < 5:
                        return None
                    height = int.from_bytes(sof[1:3], "big")
                    width = int.from_bytes(sof[3:5], "big")
                    return width, height
                fh.seek(segment_len - 2, 1)
    except Exception:
        return None

    return None


def _file_md5(path: Path, *, chunk: int = 1024 * 1024) -> str | None:
    """Full MD5 of a file, streamed in chunks to avoid loading it all at once."""
    h = hashlib.md5()
    try:
        with path.open("rb") as fh:
            while True:
                block = fh.read(chunk)
                if not block:
                    break
                h.update(block)
    except Exception:
        return None
    return h.hexdigest()


class StructureGate(BaseGate):
    """Gate 1: Verify project file structure integrity."""

    name = "structure_integrity"
    description = "Structure check: validates project file completeness and all referenced files exist"
    is_blocking = True

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []
        score = 100.0

        # Check 1: .tex files exist
        if not paper.tex_files:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    message="No .tex files found in the project",
                    suggestion="Please upload a LaTeX project containing at least one .tex file",
                )
            )
            return CheckResult(
                gate_name=self.name,
                gate_description=self.description,
                passed=False,
                score=0.0,
                issues=issues,
                summary="No .tex files found",
            )

        # Check 2: .bib file exists
        if not paper.bib_entries and not paper.bib_file_path:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    message="No .bib file found in the project",
                    suggestion="Please include a .bib bibliography file",
                )
            )
            score -= 50

        # Check 3: Main .tex identified
        main_files = [t for t in paper.tex_files if t.is_main]
        if not main_files:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    message="Could not identify the main .tex file (no \\documentclass found)",
                    suggestion="Ensure one .tex file contains both \\documentclass and \\begin{document}",
                )
            )
            score -= 10

        # Check 4: All \input{} and \include{} files exist
        for tex_file in paper.tex_files:
            for input_ref in tex_file.inputs + tex_file.includes:
                # Resolve relative to tex file's directory or project root
                ref_path = input_ref if input_ref.endswith(".tex") else f"{input_ref}.tex"
                candidates = [
                    tex_file.path.parent / ref_path,
                    paper.project_dir / ref_path,
                ]
                if not any(c.exists() for c in candidates):
                    issues.append(
                        Issue(
                            severity=Severity.ERROR,
                            message=f"Referenced file does not exist: \\input{{{input_ref}}}",
                            location=str(tex_file.path.name),
                            suggestion=f"Ensure '{ref_path}' is included in the uploaded zip",
                        )
                    )
                    score -= 15

        # Check 5: All \includegraphics{} files exist
        for tex_file in paper.tex_files:
            graphic_dirs = _graphicspath_dirs(tex_file.stripped_text, tex_file.path.parent)
            for graphic in tex_file.graphics:
                # Try with and without common extensions
                # Normalize path separators (LaTeX uses / but Windows may have \)
                graphic_norm = graphic.replace("\\", "/")
                candidates = [
                    paper.project_dir / graphic_norm,
                    tex_file.path.parent / graphic_norm,
                    # Sub-files may use paths relative to project root
                    *(paper.project_dir / p / graphic_norm
                      for p in [".", "figures", "floats", "imgs", "images", "fig"]),
                ]
                for graphic_dir in graphic_dirs:
                    candidates.append(graphic_dir / graphic_norm)
                # Inherit graphicspath from main tex file
                if paper.tex_files:
                    main_dirs = _graphicspath_dirs(
                        paper.tex_files[0].stripped_text, paper.tex_files[0].path.parent
                    )
                    for gd in main_dirs:
                        candidates.append(gd / graphic_norm)
                if not Path(graphic_norm).suffix:
                    for ext in [".png", ".pdf", ".jpg", ".jpeg", ".eps"]:
                        candidates.append(paper.project_dir / f"{graphic_norm}{ext}")
                        candidates.append(tex_file.path.parent / f"{graphic_norm}{ext}")
                        for graphic_dir in graphic_dirs:
                            candidates.append(graphic_dir / f"{graphic_norm}{ext}")

                if not any(c.exists() for c in candidates):
                    issues.append(
                        Issue(
                            severity=Severity.WARNING,
                            message=f"Image file not found: {graphic}",
                            location=str(tex_file.path.name),
                            suggestion=f"Include the image file '{graphic}' in the uploaded zip",
                        )
                    )
                    score -= 5

        # Check 5.5: \bibliography{} / \addbibresource{} points to existing .bib file
        for tex_file in paper.tex_files:
            bib_refs = []
            for bib_match in _BIBLIOGRAPHY_PATTERN.finditer(tex_file.stripped_text):
                bib_refs.extend((b.strip(), "\\bibliography") for b in bib_match.group(1).split(",") if b.strip())
            for bib_match in _ADDBIBRESOURCE_PATTERN.finditer(tex_file.stripped_text):
                bib_refs.append((bib_match.group(1).strip(), "\\addbibresource"))

            for bib_ref, command in bib_refs:
                bib_name = bib_ref if bib_ref.endswith(".bib") else f"{bib_ref}.bib"
                candidates = [
                    tex_file.path.parent / bib_name,
                    paper.project_dir / bib_name,
                ]
                if not any(c.exists() for c in candidates):
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"{command}{{{bib_ref}}} points to a non-existent file: {bib_name}",
                        location=str(tex_file.path.name),
                        file=tex_file.path.name,
                        suggestion=f"Ensure '{bib_name}' is included in the uploaded zip, or correct the filename in {command}.",
                    ))
                    score -= 15

        # Check 6: Duplicate \label definitions
        all_labels: dict[str, list[str]] = {}  # label → [files where defined]
        for tex_file in paper.tex_files:
            for label in tex_file.labels:
                if label not in all_labels:
                    all_labels[label] = []
                all_labels[label].append(tex_file.path.name)

        for label, files in all_labels.items():
            if len(files) > 1:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"Duplicate \\label{{{label}}} (defined in {len(files)} files)",
                    location=", ".join(files),
                    suggestion="Each label must be defined exactly once. Duplicate labels cause cross-references to point to the wrong location.",
                ))
                score -= 10

        # Check 7: Orphan \ref (references to non-existent labels)
        all_label_set = set(all_labels.keys())
        all_refs: dict[str, list[str]] = {}  # ref_key → [files]
        for tex_file in paper.tex_files:
            for ref in tex_file.refs:
                if ref not in all_refs:
                    all_refs[ref] = []
                all_refs[ref].append(tex_file.path.name)

        for ref_key, files in all_refs.items():
            if ref_key not in all_label_set:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"\\ref{{{ref_key}}} references a non-existent label",
                    location=files[0],
                    file=files[0],
                    suggestion=f"Create \\label{{{ref_key}}} or fix the spelling in \\ref. This will render as '??' after compilation.",
                ))
                score -= 10

        # Check 8 + 8.5: Duplicate images and image quality hints.
        # Single directory walk; collect (rel, size) once and reuse it for both
        # the duplicate scan and the quality hints to avoid re-reading files.
        image_exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
        image_files: list[tuple[Path, str, int]] = []  # (path, rel, size_bytes)
        size_groups: dict[int, list[Path]] = {}
        for img_file in paper.project_dir.rglob("*"):
            if not img_file.is_file() or img_file.suffix.lower() not in image_exts:
                continue
            try:
                rel = str(img_file.relative_to(paper.project_dir))
                size_bytes = img_file.stat().st_size
            except Exception:
                continue
            image_files.append((img_file, rel, size_bytes))
            size_groups.setdefault(size_bytes, []).append(img_file)

        # Duplicate detection: only files sharing an identical byte size can be
        # identical, so MD5 is computed only within same-size groups. Unique
        # sizes (the common case) skip hashing entirely.
        image_hashes: dict[str, list[str]] = {}
        for candidates in size_groups.values():
            if len(candidates) < 2:
                continue
            for candidate in candidates:
                h = _file_md5(candidate)
                if h is None:
                    continue
                rel = str(candidate.relative_to(paper.project_dir))
                image_hashes.setdefault(h, []).append(rel)

        for h, paths in image_hashes.items():
            if len(paths) > 1:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Duplicate image files found ({len(paths)} files with identical content)",
                    location=paths[0],
                    evidence=f"Identical files: {', '.join(paths[:4])}",
                    suggestion="These image files have identical content. If used in different figures, this may be a copy-paste error.",
                ))
                score -= 5

        # Image quality / optimization hints, reusing the collected file list.
        for img_file, rel, size_bytes in image_files:
            if size_bytes > _LARGE_IMAGE_BYTES:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Image file is too large: {rel}",
                    location=rel,
                    file=rel,
                    evidence=f"File size is approximately {size_bytes / 1024 / 1024:.1f} MB",
                    suggestion="Consider compressing raster images or PDF figures. For plots and diagrams, prefer vector PDF/SVG and avoid embedding oversized uncompressed screenshots.",
                ))
                score -= 2

            dimensions = _raster_dimensions(img_file)
            if dimensions:
                width, height = dimensions
                if min(width, height) < _LOW_RASTER_MIN_DIMENSION:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message=f"Image resolution is low: {rel}",
                        location=rel,
                        file=rel,
                        evidence=f"Detected {width}x{height}px; shortest side is below {_LOW_RASTER_MIN_DIMENSION}px",
                        suggestion="Replace with a higher-resolution image or a vector graphic to avoid blurry figures in the submitted PDF.",
                    ))
                    score -= 2

        # Check 9: Unmatched \begin{} / \end{} environments
        for tex_file in paper.tex_files:
            text = tex_file.stripped_text
            # Strip comments
            clean_lines = []
            for line in text.split("\n"):
                # Remove inline comments (but not \%)
                idx = 0
                while idx < len(line):
                    if line[idx] == '%' and (idx == 0 or line[idx-1] != '\\'):
                        line = line[:idx]
                        break
                    idx += 1
                clean_lines.append(line)
            clean = "\n".join(clean_lines)

            begins = re.findall(r"\\begin\{(\w+)\}", clean)
            ends = re.findall(r"\\end\{(\w+)\}", clean)

            begin_counts = Counter(begins)
            end_counts = Counter(ends)

            for env, count in begin_counts.items():
                end_count = end_counts.get(env, 0)
                if count > end_count:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"\\begin{{{env}}} has {count - end_count} more occurrence(s) than \\end{{{env}}} (unclosed environment)",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion=f"Ensure every \\begin{{{env}}} has a matching \\end{{{env}}}. Unclosed environments will cause compilation failure.",
                    ))
                    score -= 15

            for env, count in end_counts.items():
                begin_count = begin_counts.get(env, 0)
                if count > begin_count:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"\\end{{{env}}} has {count - begin_count} more occurrence(s) than \\begin{{{env}}} (extra closing tag)",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion=f"There is an extra \\end{{{env}}}. Check whether the corresponding \\begin{{{env}}} was accidentally deleted.",
                    ))
                    score -= 15

        passed = all(i.severity != Severity.ERROR for i in issues)
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=max(score, 0.0),
            issues=issues,
            summary=f"Structure check: {error_count} error(s), {len(issues) - error_count} warning(s)",
        )
