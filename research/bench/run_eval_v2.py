"""Run evaluation on benchmark_v2.json (full-paper mode).

Each case is a complete minimal LaTeX paper. We write it to disk,
parse with our full pipeline, then run the relevant gate.

Systems:
  B0  -- legacy naive regex (only for data_integrity)
  Ours -- current ScholarLint gates

Usage:
    python research/bench/run_eval_v2.py [--skip-llm]

Output: research/bench/eval_results_v2.json + eval_report_v2.md
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BENCH  = Path(__file__).parent / "benchmark_v2.json"
OUT_JSON = Path(__file__).parent / "eval_results_v2.json"
OUT_MD   = Path(__file__).parent / "eval_report_v2.md"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: write a full paper to a temp dir and parse it
# ─────────────────────────────────────────────────────────────────────────────

def _write_paper(tex: str, bib: str) -> Path:
    """Write tex + bib to a temp dir and return the dir path."""
    d = Path(tempfile.mkdtemp())
    (d / "main.tex").write_text(tex, encoding="utf-8")
    (d / "refs.bib").write_text(bib, encoding="utf-8")
    return d


def _parse_paper(d: Path):
    from app.parsers.tex_parser import parse_all_tex_files
    from app.parsers.bib_parser import parse_all_bib_files
    from app.models import ParsedPaper
    tex_files  = parse_all_tex_files([d / "main.tex"])
    bib_entries = parse_all_bib_files([d / "refs.bib"])
    return ParsedPaper(
        project_dir=d,
        tex_files=tex_files,
        bib_entries=bib_entries,
        all_files=list(d.iterdir()),
        figure_files=[],
    )


def _cleanup(d: Path):
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
# B0: legacy regex (data_integrity only)
# ─────────────────────────────────────────────────────────────────────────────

def _b0_predict(case: dict) -> int:
    if case["gate"] != "data_integrity":
        return 0
    # Run on perturbed then clean, return 1 if more issues in perturbed
    return 1 if _b0_issues(case["tex"]) > _b0_issues(case["clean_tex"]) else 0


def _b0_issues(tex: str) -> int:
    """Count issues from old naive regex on full tex."""
    table_vals: list[float] = []
    for line in tex.splitlines():
        if line.count("&") >= 2:
            for m in re.finditer(r"-?\d+\.\d+", line):
                try:
                    table_vals.append(float(m.group()))
                except ValueError:
                    pass
    claim_pat = re.compile(
        r"(?:achiev|obtain|reach|attain|report|get|scores?)\w*"
        r"(?:\s+\w+){0,3}?\s+(?:of\s+)?(\d+\.\d+)",
        re.IGNORECASE,
    )
    count = 0
    for line in tex.splitlines():
        if line.lstrip().startswith("%") or line.count("&") >= 2:
            continue
        for m in claim_pat.finditer(line):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            dp = len(m.group(1).split(".")[1])
            lower = 0.5 * (10 ** -dp)
            upper = min(v * 0.05, 2.0)
            for tv in table_vals:
                diff = abs(v - round(tv, dp))
                if lower <= diff <= upper:
                    count += 1
                    break
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Ours: run the actual gate (differential)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_gate(case: dict, use_perturbed: bool) -> int:
    """Return issue count from running the gate on a full paper."""
    from app.checks.gate_data import DataIntegrityGate
    from app.checks.gate_citations import CitationConsistencyGate
    from app.checks.gate_figures import FigureTableGate
    from app.models import Severity

    tex = case["tex"] if use_perturbed else case["clean_tex"]
    bib = case["bib"]
    d = _write_paper(tex, bib)
    try:
        paper = _parse_paper(d)
        gate_name = case["gate"]
        if gate_name == "data_integrity":
            result = await DataIntegrityGate().check(paper)
        elif gate_name == "citation_bib_consistency":
            result = await CitationConsistencyGate().check(paper)
        elif gate_name == "figure_table_crossref":
            result = await FigureTableGate().check(paper)
        else:
            return 0
        return sum(1 for i in result.issues
                   if i.severity in (Severity.ERROR, Severity.WARNING))
    finally:
        _cleanup(d)


async def _ours_predict(case: dict) -> int:
    p_issues = await _run_gate(case, use_perturbed=True)
    c_issues = await _run_gate(case, use_perturbed=False)
    return 1 if p_issues > c_issues else 0


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(labels: list[int], preds: list[int]) -> dict:
    tp = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 1)
    fn = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 0)
    tn = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "P": round(precision, 3), "R": round(recall, 3), "F1": round(f1, 3)}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    cases = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} cases from benchmark_v2")

    results = []
    for i, case in enumerate(cases):
        print(f"  [{i+1}/{len(cases)}] {case['id']}  label={case['label']}", end=" ... ")
        pred_b0   = _b0_predict(case)
        pred_ours = await _ours_predict(case)
        print(f"B0={pred_b0} Ours={pred_ours}")
        results.append({**case, "pred_b0": pred_b0, "pred_ours": pred_ours})

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    GATES   = ["data_integrity", "citation_bib_consistency", "figure_table_crossref"]
    SYSTEMS = [("B0 (legacy regex)", "pred_b0"), ("Ours (ScholarLint)", "pred_ours")]

    md = ["# ScholarLint Benchmark v2 (Full-Paper Mode)", "",
          f"Cases: **{len(results)}**  "
          f"(bug={sum(1 for r in results if r['label']==1)}, "
          f"clean={sum(1 for r in results if r['label']==0)})", "",
          "Evaluation method: **differential** — pred=1 iff gate(perturbed) > gate(clean)", ""]

    all_m: dict[str, dict] = {}
    for sys_name, pk in SYSTEMS:
        md += [f"## {sys_name}", "",
               "| Gate | TP | FP | FN | TN | P | R | F1 |",
               "|------|----|----|----|----|---|---|-----|"]
        gate_m = {}
        for gate in GATES:
            sub = [r for r in results if r["gate"] == gate]
            if not sub:
                continue
            m = _metrics([r["label"] for r in sub], [r[pk] for r in sub])
            gate_m[gate] = m
            md.append(f"| {gate} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} "
                      f"| {m['P']:.2f} | {m['R']:.2f} | {m['F1']:.2f} |")
        if gate_m:
            avg_p = sum(v["P"] for v in gate_m.values()) / len(gate_m)
            avg_r = sum(v["R"] for v in gate_m.values()) / len(gate_m)
            avg_f = sum(v["F1"] for v in gate_m.values()) / len(gate_m)
            md.append(f"| **Overall** | - | - | - | - "
                      f"| **{avg_p:.2f}** | **{avg_r:.2f}** | **{avg_f:.2f}** |")
        md.append("")
        all_m[sys_name] = gate_m

    # Comparison table
    md += ["## Summary (Macro F1)", "",
           "| Gate | B0 | Ours |", "|------|----|------|"]
    for gate in GATES:
        b0_f1   = all_m.get("B0 (legacy regex)", {}).get(gate, {}).get("F1", "N/A")
        ours_f1 = all_m.get("Ours (ScholarLint)", {}).get(gate, {}).get("F1", "N/A")
        b0_s   = f"{b0_f1:.2f}"   if isinstance(b0_f1, float)   else b0_f1
        ours_s = f"{ours_f1:.2f}" if isinstance(ours_f1, float) else ours_f1
        md.append(f"| {gate} | {b0_s} | {ours_s} |")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\nReport: {OUT_MD}")
    print("\n" + "\n".join(md[7:]))


if __name__ == "__main__":
    asyncio.run(main())
