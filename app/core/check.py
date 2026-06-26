"""Headless check pipeline.

Pure-function entry point for running quality gates on an already-extracted
paper folder. No FastAPI, no global state, no persistence — just folder in,
``FullReport`` out.

Use this from CLI scripts, experiment notebooks, or future API clients that
want to invoke the check engine without going through HTTP. The web service
in ``app/api/routes.py`` is a separate, untouched code path that owns its own
extraction / persistence / progress concerns.

Example
-------
    import asyncio
    from app.core.check import check_folder

    report = asyncio.run(check_folder("path/to/extracted-paper"))
    print(report.overall_score, report.overall_passed)
    for gate in report.gate_results:
        print(gate.gate_name, gate.passed, len(gate.issues))
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.checks.base import BaseGate
from app.checks.gate_citations import CitationConsistencyGate
from app.checks.gate_data import DataIntegrityGate
from app.checks.gate_figures import FigureTableGate
from app.checks.gate_references import ReferenceAuthenticityGate
from app.checks.gate_structure import StructureGate
from app.checks.gate_writing import WritingQualityGate
from app.models import FullReport
from app.parsers.bbl_parser import extract_inline_bib_entries, parse_all_bbl_files
from app.parsers.bib_parser import parse_all_bib_files
from app.parsers.tex_parser import parse_all_tex_files
from app.parsers.zip_parser import identify_project_structure


def default_gates() -> list[BaseGate]:
    """Return the canonical 6-gate suite in the order routes.py uses."""
    return [
        StructureGate(),
        CitationConsistencyGate(),
        ReferenceAuthenticityGate(),
        FigureTableGate(),
        DataIntegrityGate(),
        WritingQualityGate(),
    ]


def _word_count(raw_text: str) -> int:
    text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", " ", raw_text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"[{}$%\\]", "", text)
    return len(text.split())


async def check_folder(
    folder: Path | str,
    *,
    filename: str = "",
    job_id: str = "",
    gates: list[BaseGate] | None = None,
) -> FullReport:
    """Run quality gates on an already-extracted paper folder.

    Parameters
    ----------
    folder:
        Path to a directory that already contains the paper sources. The
        caller is responsible for any extraction or sanitisation; this
        function does not modify the folder.
    filename:
        Optional display label written into the report. Defaults to the
        folder name.
    job_id:
        Optional id written into the report. A UUID4 hex is generated when
        omitted.
    gates:
        Optional list of gates to run. Defaults to ``default_gates()``.

    Returns
    -------
    FullReport
        Pydantic model. Use ``.model_dump()`` for JSON serialisation.

    Raises
    ------
    FileNotFoundError
        If ``folder`` does not exist or is not a directory.
    """
    project_dir = Path(folder).resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Not a directory: {project_dir}")

    paper, tex_paths, bib_paths, bbl_paths = identify_project_structure(project_dir)
    paper.tex_files = parse_all_tex_files(tex_paths)
    paper.bib_entries = parse_all_bib_files(bib_paths)
    bbl_used = False
    if not paper.bib_entries and bbl_paths:
        paper.bib_entries = parse_all_bbl_files(bbl_paths)
        bbl_used = True
    # Third fallback: inline \begin{thebibliography} inside .tex files
    if not paper.bib_entries:
        paper.bib_entries = extract_inline_bib_entries(paper.tex_files)
        if paper.bib_entries:
            bbl_used = True  # treat inline same as bbl for metadata

    active_gates = gates if gates is not None else default_gates()

    report = FullReport(
        job_id=job_id or uuid.uuid4().hex,
        filename=filename or project_dir.name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        project_dir=str(project_dir),
    )

    for gate in active_gates:
        result = await gate.check(paper)
        report.gate_results.append(result)

    total_words = sum(_word_count(tf.raw_text) for tf in paper.tex_files)
    report.metadata = {
        "status": "completed",
        "word_count": total_words,
        "page_estimate": round(total_words / 500, 1),
        "bib_count": len(paper.bib_entries),
        "tex_count": len(paper.tex_files),
        "bbl_used": bbl_used,
    }

    report.compute_overall()
    return report
