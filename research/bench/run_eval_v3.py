"""Evaluate ScholarLint on benchmark_v3 (full-paper, multi-gate).

Usage:
    python research/bench/run_eval_v3.py             # all gates (refs need network)
    python research/bench/run_eval_v3.py --skip-refs # skip reference_authenticity

Systems:
    B0   -- legacy naive regex (data_integrity only)
    Ours -- ScholarLint current gates

Output: research/bench/eval_results_v3.json + eval_report_v3.md
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BENCH    = Path(__file__).parent / "benchmark_v3.json"
OUT_JSON = Path(__file__).parent / "eval_results_v3.json"
OUT_MD   = Path(__file__).parent / "eval_report_v3.md"
SKIP_REFS = "--skip-refs" in sys.argv


# ─────────────────────────────────────────────────────────────────────────────
# Paper I/O
# ─────────────────────────────────────────────────────────────────────────────

def _write_paper(case: dict, use_perturbed: bool) -> Path:
    d = Path(tempfile.mkdtemp())
    tex = case["tex"] if use_perturbed else case["clean_tex"]
    bib = case["bib"] if use_perturbed else case["clean_bib"]
    (d / "main.tex").write_text(tex, encoding="utf-8")
    (d / "refs.bib").write_text(bib, encoding="utf-8")
    # Extra files (e.g. tab_results.tex for cross-file cases)
    extra = case["extra_files"] if use_perturbed else case["clean_extra_files"]
    for fname, content in (extra or {}).items():
        (d / fname).write_text(content, encoding="utf-8")
    return d


def _parse_paper(d: Path):
    from app.parsers.tex_parser import parse_all_tex_files
    from app.parsers.bib_parser import parse_all_bib_files
    from app.models import ParsedPaper
    tex_paths = list(d.glob("*.tex"))
    bib_paths = list(d.glob("*.bib"))
    tex_files  = parse_all_tex_files(tex_paths)
    bib_entries = parse_all_bib_files(bib_paths)
    return ParsedPaper(
        project_dir=d,
        tex_files=tex_files,
        bib_entries=bib_entries,
        all_files=list(d.iterdir()),
        figure_files=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# B0: legacy regex (data_integrity only)
# ─────────────────────────────────────────────────────────────────────────────

def _b0_issues(tex: str) -> int:
    table_vals: list[float] = []
    for line in tex.splitlines():
        if line.count("&") >= 2:
            for m in re.finditer(r"-?\d+\.\d+", line):
                try:
                    table_vals.append(float(m.group()))
                except ValueError:
                    pass
    pat = re.compile(
        r"(?:achiev|obtain|reach|attain|report|get|scores?)\w*"
        r"(?:\s+\w+){0,3}?\s+(?:of\s+)?(\d+\.\d+)",
        re.IGNORECASE,
    )
    count = 0
    for line in tex.splitlines():
        if line.lstrip().startswith("%") or line.count("&") >= 2:
            continue
        for m in pat.finditer(line):
            try:
                v = float(m.group(1))
            except ValueError:
                continue
            dp = len(m.group(1).split(".")[1])
            lower = 0.5 * (10 ** -dp)
            upper = min(v * 0.05, 2.0)
            for tv in table_vals:
                if lower <= abs(v - round(tv, dp)) <= upper:
                    count += 1
                    break
    return count


def _b0_predict(case: dict) -> int:
    if case["gate"] != "data_integrity":
        return 0
    return 1 if _b0_issues(case["tex"]) > _b0_issues(case["clean_tex"]) else 0


# ─────────────────────────────────────────────────────────────────────────────
# Ours: run gate (differential)
# ─────────────────────────────────────────────────────────────────────────────

async def _run_gate(case: dict, use_perturbed: bool) -> int:
    from app.checks.gate_data import DataIntegrityGate
    from app.checks.gate_citations import CitationConsistencyGate
    from app.checks.gate_figures import FigureTableGate
    from app.checks.gate_references import ReferenceAuthenticityGate
    from app.models import Severity

    d = _write_paper(case, use_perturbed)
    try:
        paper = _parse_paper(d)
        gate_name = case["gate"]
        if gate_name == "data_integrity":
            result = await DataIntegrityGate().check(paper)
        elif gate_name == "citation_bib_consistency":
            result = await CitationConsistencyGate().check(paper)
        elif gate_name == "figure_table_crossref":
            result = await FigureTableGate().check(paper)
        elif gate_name == "reference_authenticity":
            if SKIP_REFS:
                return -1  # skip
            result = await ReferenceAuthenticityGate().check(paper)
            # Reference gate: count ERROR only — warnings are noisy (title similarity,
            # venue abbreviation) and symmetric across perturbed/clean, cancelling signal.
            return sum(1 for i in result.issues if i.severity == Severity.ERROR)
        else:
            return 0
        return sum(1 for i in result.issues
                   if i.severity in (Severity.ERROR, Severity.WARNING))
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def _ours_predict(case: dict) -> int:
    p = await _run_gate(case, True)
    c = await _run_gate(case, False)
    if p == -1 or c == -1:
        return -1  # skipped
    return 1 if p > c else 0


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(labels: list[int], preds: list[int]) -> dict:
    pairs = [(y, p) for y, p in zip(labels, preds) if p != -1]
    if not pairs:
        return {"TP": 0, "FP": 0, "FN": 0, "TN": 0,
                "P": 0.0, "R": 0.0, "F1": 0.0, "N": 0}
    ys, ps = zip(*pairs)
    tp = sum(1 for y, p in zip(ys, ps) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(ys, ps) if y == 0 and p == 1)
    fn = sum(1 for y, p in zip(ys, ps) if y == 1 and p == 0)
    tn = sum(1 for y, p in zip(ys, ps) if y == 0 and p == 0)
    pr = tp / (tp + fp) if (tp + fp) else 0.0
    rc = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "P": round(pr, 3), "R": round(rc, 3), "F1": round(f1, 3), "N": len(pairs)}


# ─────────────────────────────────────────────────────────────────────────────
# Report builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_report(results: list[dict]) -> str:
    GATES = ["data_integrity", "citation_bib_consistency",
             "figure_table_crossref", "reference_authenticity"]
    SYSTEMS = [("B0 (legacy regex)", "pred_b0"),
               ("Ours (ScholarLint)", "pred_ours")]

    lines = [
        "# ScholarLint Benchmark v3",
        "",
        f"Cases: **{len(results)}**  "
        f"(bug={sum(1 for r in results if r['label']==1)}, "
        f"clean={sum(1 for r in results if r['label']==0)})",
        "",
        "Perturbation types: P1, P1_xfile, P3, P4, P5, P6, R1, R2, R3",
        "Eval method: **differential** — pred=1 iff issues(perturbed) > issues(clean)",
        "",
    ]

    all_m: dict[str, dict] = {}
    for sys_name, pk in SYSTEMS:
        lines += [f"## {sys_name}", "",
                  "| Gate | TP | FP | FN | TN | P | R | F1 | N |",
                  "|------|----|----|----|----|----|---|-----|---|"]
        gm = {}
        for gate in GATES:
            sub = [r for r in results if r["gate"] == gate]
            if not sub:
                continue
            m = _metrics([r["label"] for r in sub],
                         [r.get(pk, -1) for r in sub])
            gm[gate] = m
            skip_note = " *(skipped)*" if m["N"] == 0 else ""
            lines.append(
                f"| {gate}{skip_note} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} "
                f"| {m['P']:.2f} | {m['R']:.2f} | {m['F1']:.2f} | {m['N']} |"
            )
        valid = [v for v in gm.values() if v["N"] > 0]
        if valid:
            ap = sum(v["P"] for v in valid) / len(valid)
            ar = sum(v["R"] for v in valid) / len(valid)
            af = sum(v["F1"] for v in valid) / len(valid)
            lines.append(
                f"| **Overall (macro)** | - | - | - | - "
                f"| **{ap:.2f}** | **{ar:.2f}** | **{af:.2f}** | - |"
            )
        lines.append("")
        all_m[sys_name] = gm

    # Summary table
    lines += ["## Summary: Macro F1", "",
              "| Gate | B0 | Ours |", "|------|----|------|"]
    for gate in GATES:
        def gf(name):
            v = all_m.get(name, {}).get(gate, {})
            f = v.get("F1")
            n = v.get("N", 0)
            if n == 0:
                return "skip"
            return f"{f:.2f}" if f is not None else "N/A"
        lines.append(f"| {gate} | {gf('B0 (legacy regex)')} | {gf('Ours (ScholarLint)')} |")
    lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    cases = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} cases  (--skip-refs={SKIP_REFS})")

    results = []
    for i, case in enumerate(cases):
        pred_b0   = _b0_predict(case)
        pred_ours = await _ours_predict(case)
        label     = case["label"]
        status = ("TP" if pred_ours==1 and label==1 else
                  "TN" if pred_ours==0 and label==0 else
                  "FP" if pred_ours==1 and label==0 else
                  "FN" if pred_ours==0 and label==1 else "SKIP")
        print(f"  [{i+1:3d}/{len(cases)}] {case['id'][:50]:<52} "
              f"label={label} ours={pred_ours} [{status}]")
        results.append({**case, "pred_b0": pred_b0, "pred_ours": pred_ours})

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    report = _build_report(results)
    OUT_MD.write_text(report, encoding="utf-8")
    print(f"\nReport:\n{report}")


if __name__ == "__main__":
    asyncio.run(main())
