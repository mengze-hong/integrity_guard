"""False-positive audit: run all non-network gates on the real papers under
uploads/ and tally what each gate flags.

These are real submitted papers, so most flagged ERRORs on them are candidate
false positives worth eyeballing. Reference authenticity is skipped (needs live
external APIs); everything else is local and deterministic.

Run:  python research/bench/audit_fp.py
Out:  research/bench/audit_report.md
"""

from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from pathlib import Path

from app.checks.gate_citations import CitationConsistencyGate
from app.checks.gate_data import DataIntegrityGate
from app.checks.gate_figures import FigureTableGate
from app.checks.gate_structure import StructureGate
from app.checks.gate_writing import WritingQualityGate
from app.models import Severity
from app.parsers.bbl_parser import extract_inline_bib_entries, parse_all_bbl_files
from app.parsers.bib_parser import parse_all_bib_files
from app.parsers.tex_parser import parse_all_tex_files
from app.parsers.zip_parser import identify_project_structure

ROOT = Path(__file__).resolve().parents[2]
UPLOADS = ROOT / "uploads"
OUT = Path(__file__).resolve().parent / "audit_report.md"

# Local, non-network gates only.
GATES = [
    StructureGate(),
    CitationConsistencyGate(),
    FigureTableGate(),
    DataIntegrityGate(),
    WritingQualityGate(),
]


def _parse(folder: Path):
    paper, tex_paths, bib_paths, bbl_paths = identify_project_structure(folder)
    paper.tex_files = parse_all_tex_files(tex_paths)
    paper.bib_entries = parse_all_bib_files(bib_paths)
    if not paper.bib_entries and bbl_paths:
        paper.bib_entries = parse_all_bbl_files(bbl_paths)
    if not paper.bib_entries:
        paper.bib_entries = extract_inline_bib_entries(paper.tex_files)
    return paper


async def audit_one(folder: Path):
    paper = _parse(folder)
    per_gate = {}
    for gate in GATES:
        try:
            result = await gate.check(paper)
        except Exception as exc:  # noqa: BLE001 - audit must not crash on one paper
            per_gate[gate.name] = {"error": repr(exc)}
            continue
        errs = [i for i in result.issues if i.severity == Severity.ERROR]
        warns = [i for i in result.issues if i.severity == Severity.WARNING]
        per_gate[gate.name] = {
            "score": result.score,
            "passed": result.passed,
            "errors": errs,
            "warnings": warns,
        }
    return per_gate


async def main():
    folders = sorted(p for p in UPLOADS.iterdir() if p.is_dir())
    # message-prefix tally per gate/severity to spot systematic false positives
    err_msgs: dict[str, Counter] = defaultdict(Counter)
    warn_msgs: dict[str, Counter] = defaultdict(Counter)
    papers_with_err: dict[str, int] = Counter()
    n_papers = 0
    detail_lines = []

    for folder in folders:
        paper_files = list(folder.rglob("*.tex"))
        if not paper_files:
            continue
        n_papers += 1
        per_gate = await audit_one(folder)
        detail_lines.append(f"\n### {folder.name}")
        for gname, info in per_gate.items():
            if "error" in info:
                detail_lines.append(f"- **{gname}**: CRASH {info['error']}")
                continue
            e, w = len(info["errors"]), len(info["warnings"])
            if e:
                papers_with_err[gname] += 1
            detail_lines.append(
                f"- **{gname}**: score={info['score']:.0f} pass={info['passed']} "
                f"errors={e} warnings={w}"
            )
            for iss in info["errors"]:
                key = iss.message.split("（")[0].split(":")[0][:40]
                err_msgs[gname][key] += 1
                detail_lines.append(f"    - [E] {iss.message[:90]}")
            for iss in info["warnings"]:
                key = iss.message.split("（")[0].split(":")[0][:40]
                warn_msgs[gname][key] += 1

    lines = [
        "# False-Positive Audit Report",
        "",
        f"Papers audited: **{n_papers}** (real submissions under `uploads/`)",
        "Gates: structure, citations, figures, data, writing "
        "(reference authenticity skipped — needs live APIs).",
        "",
        "> On real published/submitted papers, most ERRORs are **candidate "
        "false positives**. High-frequency messages = systematic FP to fix first.",
        "",
        "## ERROR frequency by gate (papers flagged / total)",
        "",
    ]
    for gname in [g.name for g in GATES]:
        lines.append(f"### {gname} — {papers_with_err[gname]}/{n_papers} papers with ≥1 error")
        for msg, cnt in err_msgs[gname].most_common(12):
            lines.append(f"- `{cnt}×` {msg}")
        if not err_msgs[gname]:
            lines.append("- (no errors)")
        lines.append("")

    lines.append("## WARNING frequency by gate (top messages)")
    lines.append("")
    for gname in [g.name for g in GATES]:
        top = warn_msgs[gname].most_common(8)
        if not top:
            continue
        lines.append(f"### {gname}")
        for msg, cnt in top:
            lines.append(f"- `{cnt}×` {msg}")
        lines.append("")

    lines.append("## Per-paper detail")
    lines.extend(detail_lines)

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Audited {n_papers} papers.")
    for gname in [g.name for g in GATES]:
        print(f"  {gname}: {papers_with_err[gname]}/{n_papers} papers flagged with errors")


if __name__ == "__main__":
    asyncio.run(main())
