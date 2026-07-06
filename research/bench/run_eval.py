"""Run three systems on the benchmark and compute Precision/Recall/F1.

Systems:
  B0  -- old naive regex (_check_text_table_consistency, already in gate_data.py)
  B1  -- GPT-4o zero-shot (requires LLM_API_KEY in env)
  Ours -- current ScholarLint gates

Usage:
    python research/bench/run_eval.py [--skip-llm]

Output: research/bench/eval_results.json + eval_report.md
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BENCH = Path(__file__).parent / "benchmark.json"
OUT_JSON = Path(__file__).parent / "eval_results.json"
OUT_MD = Path(__file__).parent / "eval_report.md"

SKIP_LLM = "--skip-llm" in sys.argv


# ─────────────────────────────────────────────────────────────────────────────
# B0: legacy regex
# ─────────────────────────────────────────────────────────────────────────────

def _b0_predict(case: dict) -> int:
    """Old naive regex approach for data_integrity only."""
    if case["gate"] != "data_integrity":
        return 0  # B0 had no impl for citations/figures
    snippet = case["tex_snippet"]
    # Replicate old _check_text_table_consistency logic:
    # flag if a text claim value is close (< 5%) but not equal to a table value
    table_vals: list[float] = []
    for line in snippet.splitlines():
        if line.count("&") >= 2:
            for m in re.finditer(r"-?\d+\.\d+", line):
                try:
                    table_vals.append(float(m.group()))
                except ValueError:
                    pass
    claim_pat = re.compile(
        r"(?:achiev|obtain|reach|attain|report|get|score)\w*"
        r"(?:\s+\w+){0,3}?\s+(?:of\s+)?(\d+\.\d+)",
        re.IGNORECASE,
    )
    for line in snippet.splitlines():
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
                    return 1
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# B1: GPT-4o zero-shot
# ─────────────────────────────────────────────────────────────────────────────

B1_PROMPTS = {
    "data_integrity": (
        "You are an academic integrity checker. Given this LaTeX snippet, "
        "does any numeric claim in the text (outside tables) contradict the "
        "values in the tables? Reply with a single JSON: {\"bug\": true/false, \"reason\": \"...\"}"
    ),
    "citation_bib_consistency": (
        "You are an academic integrity checker. Given this LaTeX snippet, "
        "are there any \\cite{key} commands that appear to reference keys not "
        "defined in a .bib (i.e., undefined citations)? "
        "Reply with a single JSON: {\"bug\": true/false, \"reason\": \"...\"}"
    ),
    "figure_table_crossref": (
        "You are an academic integrity checker. Given this LaTeX snippet, "
        "are there any \\ref{} commands pointing to labels that do not exist "
        "in any \\label{} definition in the snippet? "
        "Reply with a single JSON: {\"bug\": true/false, \"reason\": \"...\"}"
    ),
}


async def _b1_predict_one(case: dict, llm_check_fn) -> int:
    system = B1_PROMPTS.get(case["gate"], B1_PROMPTS["data_integrity"])
    user = f"LaTeX snippet:\n```latex\n{case['tex_snippet'][:3000]}\n```"
    try:
        raw = await llm_check_fn(
            system_prompt=system,
            user_prompt=user,
            temperature=0.0,
            max_tokens=200,
        )
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data = json.loads(raw)
        return 1 if data.get("bug") else 0
    except Exception as e:
        print(f"  B1 error: {e}")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Ours: run actual gates on modified tex
# ─────────────────────────────────────────────────────────────────────────────

async def _ours_predict(case: dict) -> int:
    """Run the relevant gate and return 1 if MORE issues found vs clean baseline.

    Uses differential evaluation: pred=1 iff gate(perturbed) > gate(clean).
    This isolates the perturbation signal from pre-existing issues in the paper.
    """
    perturbed_score = await _run_gate_on_snippet(case["tex_snippet"], case)
    clean_score = await _run_gate_on_snippet(case["clean_snippet"], case)
    # Bug detected = more issues in perturbed version than clean version
    return 1 if perturbed_score > clean_score else 0


async def _run_gate_on_snippet(snippet: str, case: dict) -> int:
    """Return issue count from running the gate on a tex snippet."""
    import os, tempfile
    from app.models import ParsedPaper, TexFile, BibEntry
    from app.checks.gate_data import DataIntegrityGate
    from app.checks.gate_citations import CitationConsistencyGate
    from app.checks.gate_figures import FigureTableGate
    from app.models import Severity
    from app.parsers.tex_parser import parse_tex_file

    gate_name = case["gate"]

    # Parse through temp file to get proper citations/stripped_text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tex",
                                    delete=False, encoding="utf-8") as f:
        f.write(snippet)
        tmp = f.name
    try:
        parsed = parse_tex_file(Path(tmp))
        tex = TexFile(
            path=Path("bench_test.tex"),
            is_main=True,
            raw_text=snippet,
            citations=parsed.citations,
            stripped_text=parsed.stripped_text,
        )
    finally:
        os.unlink(tmp)

    # Build bib_entries from clean_snippet (real keys = "bib")
    bib_entries: list[BibEntry] = []
    if gate_name == "citation_bib_consistency":
        for m in re.finditer(r"\\cite\w*\{([^}]+)\}", case["clean_snippet"]):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    bib_entries.append(BibEntry(key=k, entry_type="article"))

    paper = ParsedPaper(
        project_dir=Path("."),
        tex_files=[tex],
        bib_entries=bib_entries,
        all_files=[],
        figure_files=[],
    )

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


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(labels: list[int], preds: list[int]) -> dict:
    tp = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 1)
    fn = sum(1 for y, p in zip(labels, preds) if y == 1 and p == 0)
    tn = sum(1 for y, p in zip(labels, preds) if y == 0 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "P": round(precision, 3), "R": round(recall, 3), "F1": round(f1, 3)}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    cases = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} benchmark cases")

    llm_check = None
    if not SKIP_LLM:
        try:
            from app.services.llm import llm_check as _lc
            from app.config import settings
            if settings.llm_api_key:
                llm_check = _lc
                print("LLM available, will run B1")
            else:
                print("LLM_API_KEY not set, skipping B1")
        except Exception as e:
            print(f"LLM not available ({e}), skipping B1")

    results = []
    for i, case in enumerate(cases):
        print(f"  [{i+1}/{len(cases)}] {case['id']} label={case['label']}")
        pred_b0 = _b0_predict(case)
        pred_ours = await _ours_predict(case)
        pred_b1 = (await _b1_predict_one(case, llm_check)) if llm_check else None

        results.append({
            **case,
            "pred_b0": pred_b0,
            "pred_ours": pred_ours,
            "pred_b1": pred_b1,
        })

    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {OUT_JSON}")

    # ── Report ────────────────────────────────────────────────────────────────
    GATES = ["data_integrity", "citation_bib_consistency", "figure_table_crossref"]
    SYSTEMS = [("B0 (legacy regex)", "pred_b0"),
               ("Ours (ScholarLint)", "pred_ours")]
    if llm_check:
        SYSTEMS.append(("B1 (GPT-4o zero-shot)", "pred_b1"))

    md_lines = [
        "# ScholarLint Benchmark Evaluation",
        "",
        f"Total cases: **{len(results)}** "
        f"(bug={sum(1 for r in results if r['label']==1)}, "
        f"clean={sum(1 for r in results if r['label']==0)})",
        "",
    ]

    all_metrics: dict[str, dict[str, dict]] = {}  # system -> gate -> metrics

    for sys_name, pred_key in SYSTEMS:
        md_lines.append(f"## {sys_name}")
        md_lines.append("")
        md_lines.append("| Gate | TP | FP | FN | TN | P | R | F1 |")
        md_lines.append("|------|----|----|----|----|---|---|-----|")
        gate_metrics = {}
        for gate in GATES:
            subset = [r for r in results if r["gate"] == gate and r.get(pred_key) is not None]
            if not subset:
                continue
            labels = [r["label"] for r in subset]
            preds = [r[pred_key] for r in subset]
            m = _metrics(labels, preds)
            gate_metrics[gate] = m
            md_lines.append(
                f"| {gate} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} "
                f"| {m['P']:.2f} | {m['R']:.2f} | {m['F1']:.2f} |"
            )
        # Overall (macro avg)
        if gate_metrics:
            avg_p = sum(v["P"] for v in gate_metrics.values()) / len(gate_metrics)
            avg_r = sum(v["R"] for v in gate_metrics.values()) / len(gate_metrics)
            avg_f = sum(v["F1"] for v in gate_metrics.values()) / len(gate_metrics)
            md_lines.append(
                f"| **Overall (macro)** | - | - | - | - "
                f"| **{avg_p:.2f}** | **{avg_r:.2f}** | **{avg_f:.2f}** |"
            )
        md_lines.append("")
        all_metrics[sys_name] = gate_metrics

    # Comparison table
    md_lines += [
        "## Summary Comparison (Macro F1)",
        "",
        "| Gate | B0 | Ours |" + (" B1 (GPT-4o) |" if llm_check else ""),
        "|------|----|------|" + ("------------|" if llm_check else ""),
    ]
    for gate in GATES:
        row = f"| {gate} "
        for sys_name, _ in SYSTEMS:
            m = all_metrics.get(sys_name, {}).get(gate, {})
            row += f"| {m.get('F1', 'N/A'):.2f} " if m else "| N/A "
        row += "|"
        md_lines.append(row)
    md_lines.append("")

    OUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Report saved to {OUT_MD}")
    print("\n" + "\n".join(md_lines[5:]))


if __name__ == "__main__":
    asyncio.run(main())
