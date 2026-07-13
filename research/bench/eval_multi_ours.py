"""Evaluate ScholarLint on the MULTI-ISSUE benchmark (comprehensiveness).

Unlike the binary v3 eval, here each paper has K injected issues and we
measure how many ScholarLint recovers:

  * recall   = detected injected issues / total injected issues
  * per-type recall (data_claim / undefined_citation / dangling_ref /
                      invalid_doi / title_mismatch / author_mismatch)
  * false positives on CLEAN papers (issues flagged where there are none)
  * issues found per paper, wall-clock latency per paper

An injected issue is "detected" iff any ScholarLint issue text (message +
location + evidence + suggestion + file) contains the issue's ground-truth
key (a cite key, ref label, bib key, or the tampered number).

Usage:
    python research/bench/eval_multi_ours.py             # all gates (refs need network)
    python research/bench/eval_multi_ours.py --skip-refs # skip reference gate

Out: research/bench/eval_multi_ours.json
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BENCH = Path(__file__).parent / "benchmark_multi.json"
OUT = Path(__file__).parent / "eval_multi_ours.json"
SKIP_REFS = "--skip-refs" in sys.argv


def _write_paper(paper: dict) -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "main.tex").write_text(paper["tex"], encoding="utf-8")
    (d / "refs.bib").write_text(paper["bib"], encoding="utf-8")
    for fname, content in (paper.get("extra_files") or {}).items():
        (d / fname).write_text(content, encoding="utf-8")
    return d


def _parse_paper(d: Path):
    from app.parsers.tex_parser import parse_all_tex_files
    from app.parsers.bib_parser import parse_all_bib_files
    from app.models import ParsedPaper
    return ParsedPaper(
        project_dir=d,
        tex_files=parse_all_tex_files(list(d.glob("*.tex"))),
        bib_entries=parse_all_bib_files(list(d.glob("*.bib"))),
        all_files=list(d.iterdir()),
        figure_files=[],
    )


async def _all_issues(paper: dict) -> list[dict]:
    """Run all four gates; return a flat list of {gate, text} issue records."""
    from app.checks.gate_data import DataIntegrityGate
    from app.checks.gate_citations import CitationConsistencyGate
    from app.checks.gate_figures import FigureTableGate
    from app.checks.gate_references import ReferenceAuthenticityGate

    d = _write_paper(paper)
    try:
        p = _parse_paper(d)
        gates = [
            ("data_integrity", DataIntegrityGate()),
            ("citation_bib_consistency", CitationConsistencyGate()),
            ("figure_table_crossref", FigureTableGate()),
        ]
        if not SKIP_REFS:
            gates.append(("reference_authenticity", ReferenceAuthenticityGate()))

        found: list[dict] = []
        for gate_name, gate in gates:
            result = await gate.check(p)
            for iss in result.issues:
                sev = iss.severity.value
                # Reference gate emits advisory WARNINGs (venue-name style,
                # "use official citation format") that are not integrity
                # accusations — count ERROR only, matching the v3 methodology.
                # Fabrication signals (bad DOI, title/author mismatch) are ERROR.
                if gate_name == "reference_authenticity" and sev != "error":
                    continue
                text = " ".join(str(x) for x in [
                    iss.message, iss.location, iss.evidence or "",
                    iss.suggestion or "", getattr(iss, "file", "") or "",
                ]).lower()
                found.append({"gate": gate_name, "severity": sev, "text": text})
        return found
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _detected(gt_issue: dict, found: list[dict]) -> bool:
    """A GT issue is detected iff some found issue's text contains its key."""
    key = str(gt_issue["key"]).lower()
    return any(key in f["text"] for f in found)


async def main():
    papers = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(papers)} papers  (--skip-refs={SKIP_REFS})")

    per_paper = []
    for i, paper in enumerate(papers):
        t0 = time.time()
        found = await _all_issues(paper)
        dt = time.time() - t0

        gt = paper["issues"]
        if SKIP_REFS:
            gt = [g for g in gt if g["gate"] != "reference_authenticity"]

        detected = [g for g in gt if _detected(g, found)]
        rec = {
            "id": paper["id"], "label": paper["label"],
            "n_injected": len(gt),
            "n_detected": len(detected),
            "n_flagged": len(found),
            "detected_ids": [g["issue_id"] for g in detected],
            "missed": [{"type": g["type"], "key": g["key"]} for g in gt
                       if g not in detected],
            "latency_s": round(dt, 2),
        }
        per_paper.append(rec)
        tag = "clean" if paper["label"] == "clean" else f"{len(detected)}/{len(gt)}"
        print(f"  [{i+1:3d}/{len(papers)}] {paper['id']:<24} "
              f"detected={tag:<7} flagged={len(found):<3} {dt:.1f}s")

    # Aggregate
    buggy = [r for r in per_paper if r["label"] == "buggy"]
    clean = [r for r in per_paper if r["label"] == "clean"]
    tot_inj = sum(r["n_injected"] for r in buggy)
    tot_det = sum(r["n_detected"] for r in buggy)

    # Per-type recall
    from collections import defaultdict
    type_tot, type_det = defaultdict(int), defaultdict(int)
    for paper in papers:
        found_ids = next((r["detected_ids"] for r in per_paper if r["id"] == paper["id"]), [])
        for g in paper["issues"]:
            if SKIP_REFS and g["gate"] == "reference_authenticity":
                continue
            type_tot[g["type"]] += 1
            if g["issue_id"] in found_ids:
                type_det[g["type"]] += 1

    fp_clean = sum(r["n_flagged"] for r in clean)

    summary = {
        "papers": len(papers), "buggy": len(buggy), "clean": len(clean),
        "micro_recall": round(tot_det / tot_inj, 3) if tot_inj else 0.0,
        "injected_total": tot_inj, "detected_total": tot_det,
        "mean_detected_per_buggy": round(tot_det / len(buggy), 2) if buggy else 0.0,
        "mean_injected_per_buggy": round(tot_inj / len(buggy), 2) if buggy else 0.0,
        "false_positives_on_clean": fp_clean,
        "clean_papers_with_zero_fp": sum(1 for r in clean if r["n_flagged"] == 0),
        "mean_latency_s": round(sum(r["latency_s"] for r in per_paper) / len(per_paper), 2),
        "per_type_recall": {k: {"detected": type_det[k], "total": type_tot[k],
                                "recall": round(type_det[k] / type_tot[k], 3) if type_tot[k] else 0.0}
                            for k in sorted(type_tot)},
    }

    OUT.write_text(json.dumps({"summary": summary, "per_paper": per_paper},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== ScholarLint (Ours) — multi-issue comprehensiveness ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
