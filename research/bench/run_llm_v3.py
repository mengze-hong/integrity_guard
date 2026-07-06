"""LLM baseline evaluation on benchmark_v3.

Design principles:
1. LLM sees full paper (tex + bib), same as our system — fair comparison
2. Per-gate targeted prompts — not generic "find bugs"
3. Differential eval: pred=1 iff LLM flags more issues in perturbed vs clean
4. Models: gpt-5.5 (reasoning) + claude-opus-4.7
5. 4 parallel workers to balance speed vs rate limits
6. Resume support: saves after each prediction

Usage:
    python research/bench/run_llm_v3.py
    python research/bench/run_llm_v3.py --models gpt-5.5          # single model
    python research/bench/run_llm_v3.py --models claude-opus-4.7
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB  = Path(r"C:\Users\mengzehong\Desktop\UXBench\uxbench-v1.0\2_pipeline")
sys.path.insert(0, str(LIB))
sys.path.insert(0, str(ROOT))

from lib.llm_client import call_llm  # noqa: E402

BENCH    = Path(__file__).parent / "benchmark_v3.json"
OUT_JSON = Path(__file__).parent / "eval_llm_v3.json"
OUT_MD   = Path(__file__).parent / "eval_llm_v3.md"

# Parse --models flag
_model_arg = None
for i, arg in enumerate(sys.argv):
    if arg == "--models" and i+1 < len(sys.argv):
        _model_arg = sys.argv[i+1]

MODELS = [_model_arg] if _model_arg else ["gpt-5.5", "claude-opus-4.7"]

# ─────────────────────────────────────────────────────────────────────────────
# Per-gate prompts
# Each prompt is carefully scoped to what the gate actually checks.
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "data_integrity": """\
You are an academic integrity expert. Your task: check whether numeric \
claims in the PROSE (non-table text) of this LaTeX paper are consistent \
with the values in the paper's tables.

Specifically:
- Find sentences like "our model achieves X on dataset Y"
- Find the corresponding cell in a table (same metric, same model row)
- Flag if the text value and table value disagree at the stated precision

Important:
- Only compare claims about THIS paper's own model results (not cited works)
- Skip rows in tables (lines with &); focus on prose sentences
- A difference of ≥ 0.1 at 1 decimal place IS a bug

Respond with exactly: {"has_bug": true/false, "reason": "one sentence"}""",

    "citation_bib_consistency": """\
You are a LaTeX expert. Your task: check whether every \\cite{key} or \
\\citep{key} or \\citet{key} command in this paper has a matching entry \
in the .bib file.

Rules:
- A bug exists if any cite key used in the .tex is NOT defined in the .bib
- Ignore cite keys inside TeX comments (lines starting with %)
- The bib file is provided after "=== BIBLIOGRAPHY ==="

Respond with exactly: {"has_bug": true/false, "reason": "one sentence citing the missing key if any"}""",

    "figure_table_crossref": """\
You are a LaTeX expert. Your task: check whether every \\ref{label} \
command in this paper has a matching \\label{label} definition.

Rules:
- A bug exists if any \\ref{x} appears but \\label{x} is absent
- Check both \\ref{} and \\cref{} and \\autoref{}
- Ignore refs that are clearly to equations (eq:...) if no label exists
- Only check figure (fig:...) and table (tab:...) references

Respond with exactly: {"has_bug": true/false, "reason": "one sentence"}""",

    "reference_authenticity": """\
You are an academic librarian with expertise in verifying bibliographic \
metadata. Your task: check the .bib entries in this paper for internal \
consistency and plausibility.

Check for:
1. DOI format validity (must start with 10. followed by 4+ digits, then /)
2. Whether title and author fields look plausible (not obviously scrambled/fake)
3. Whether the number of authors seems realistic for the stated venue/year

Note: You do NOT have internet access. Judge based on:
- Is the DOI format valid? (10.NNNNN/... pattern)
- Does the title read like a real paper title?
- Are author names plausible (real-sounding names, not obviously invented)?
- Does author count match what's typical?

Respond with exactly: {"has_bug": true/false, "reason": "one sentence"}""",
}


def _build_prompt(case: dict) -> str:
    """Build the user message for a case."""
    tex = case["tex"]
    bib = case["bib"]
    # Include extra files (e.g. tab_mnli.tex) inline
    extra = case.get("extra_files", {})
    extra_text = ""
    if extra:
        parts = []
        for fname, content in extra.items():
            parts.append(f"=== EXTRA FILE: {fname} ===\n{content}")
        extra_text = "\n\n" + "\n\n".join(parts)

    gate = case["gate"]
    if gate == "citation_bib_consistency" or gate == "reference_authenticity":
        # Include bib explicitly labelled
        return (
            f"=== LaTeX SOURCE ===\n{tex}{extra_text}\n\n"
            f"=== BIBLIOGRAPHY ===\n{bib}"
        )
    else:
        return f"=== LaTeX SOURCE ===\n{tex}{extra_text}"


def _parse_response(raw: str) -> int | None:
    """Parse LLM response to 0/1. Returns None on parse failure."""
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    # Try JSON parse
    try:
        data = json.loads(raw)
        return 1 if data.get("has_bug") else 0
    except Exception:
        pass
    # Fallback: look for true/false
    if re.search(r'"has_bug"\s*:\s*true', raw, re.IGNORECASE):
        return 1
    if re.search(r'"has_bug"\s*:\s*false', raw, re.IGNORECASE):
        return 0
    return None


def _call_one(case: dict, model: str, use_perturbed: bool) -> int | None:
    """Call the LLM on one case (perturbed or clean). Returns issue count (0 or 1)."""
    # Build a version of the case with either perturbed or clean content
    view = dict(case)
    if not use_perturbed:
        view["tex"] = case["clean_tex"]
        view["bib"] = case["clean_bib"]
        view["extra_files"] = case.get("clean_extra_files", {})

    system = SYSTEM_PROMPTS[case["gate"]]
    user   = _build_prompt(view)
    msgs   = [{"role": "system", "content": system},
              {"role": "user",   "content": user}]

    # gpt-5.5 doesn't support temperature parameter at all
    kwargs = {"max_tokens": 200}
    if model.startswith("gpt-5"):
        kwargs["temperature"] = None   # omit temperature for reasoning models
    else:
        kwargs["temperature"] = 0.0

    result = call_llm(msgs, model=model, **kwargs)
    if not result.ok:
        return None
    return _parse_response(result.content or "")


def _predict(case: dict, model: str) -> int:
    """Differential prediction: 1 if LLM flags bug in perturbed but not clean."""
    p = _call_one(case, model, use_perturbed=True)
    c = _call_one(case, model, use_perturbed=False)
    if p is None or c is None:
        return -1  # error
    # Differential: perturbed flagged AND clean not flagged
    if p == 1 and c == 0:
        return 1
    # Also count as detected if perturbed has MORE confidence (both 1 but perturbed more certain)
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────

def _metrics(labels: list[int], preds: list[int]) -> dict:
    pairs = [(y, p) for y, p in zip(labels, preds) if p != -1]
    if not pairs:
        return {"TP":0,"FP":0,"FN":0,"TN":0,"P":0.0,"R":0.0,"F1":0.0,"N":0}
    ys, ps = zip(*pairs)
    tp = sum(1 for y,p in zip(ys,ps) if y==1 and p==1)
    fp = sum(1 for y,p in zip(ys,ps) if y==0 and p==1)
    fn = sum(1 for y,p in zip(ys,ps) if y==1 and p==0)
    tn = sum(1 for y,p in zip(ys,ps) if y==0 and p==0)
    pr = tp/(tp+fp) if tp+fp else 0.0
    rc = tp/(tp+fn) if tp+fn else 0.0
    f1 = 2*pr*rc/(pr+rc) if pr+rc else 0.0
    return {"TP":tp,"FP":fp,"FN":fn,"TN":tn,
            "P":round(pr,3),"R":round(rc,3),"F1":round(f1,3),"N":len(pairs)}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    cases = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} cases. Models: {MODELS}")

    # Load or init results
    if OUT_JSON.exists():
        results = {r["id"]: r for r in json.loads(OUT_JSON.read_text(encoding="utf-8"))}
        print(f"Resuming from {len(results)} cached results")
    else:
        results = {c["id"]: dict(c) for c in cases}

    GATES = ["data_integrity", "citation_bib_consistency",
             "figure_table_crossref", "reference_authenticity"]

    for model in MODELS:
        pk = f"pred_{model.replace('-','_').replace('.','_')}"
        todo = [c for c in cases if results[c["id"]].get(pk) is None]
        cached = len(cases) - len(todo)
        print(f"\n{'='*60}")
        print(f"Model: {model}  ({cached} cached, {len(todo)} to run)")

        def run_one(case):
            pred = _predict(case, model)
            return case["id"], pred

        # 4 parallel workers
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(run_one, c): c for c in todo}
            done = 0
            for fut in as_completed(futures):
                cid, pred = fut.result()
                results[cid][pk] = pred
                done += 1
                label = results[cid]["label"]
                gate  = results[cid]["gate"]
                status = ("TP" if pred==1 and label==1 else
                          "TN" if pred==0 and label==0 else
                          "FP" if pred==1 and label==0 else
                          "FN" if pred==0 and label==1 else "ERR")
                print(f"  [{done:3d}/{len(todo)}] {cid[:50]:<52} {status}")
                # Save after each for resume
                OUT_JSON.write_text(
                    json.dumps(list(results.values()), indent=2, ensure_ascii=False),
                    encoding="utf-8")

    # ── Build report ──────────────────────────────────────────────────────────
    all_results = list(results.values())

    # Load Ours results for comparison
    ours_file = Path(__file__).parent / "eval_results_v3.json"
    ours_map = {}
    if ours_file.exists():
        for r in json.loads(ours_file.read_text(encoding="utf-8")):
            ours_map[r["id"]] = r.get("pred_ours")

    # System list: Ours + each LLM model
    systems = [("Ours (ScholarLint)", "pred_ours", ours_map)]
    for model in MODELS:
        pk = f"pred_{model.replace('-','_').replace('.','_')}"
        systems.append((model, pk, None))

    md = [
        "# ScholarLint LLM Baseline — benchmark_v3",
        "",
        f"**{len(all_results)} cases** (bug={sum(1 for r in all_results if r['label']==1)}, "
        f"clean={sum(1 for r in all_results if r['label']==0)})",
        "",
        "Eval: differential (pred=1 iff LLM flags perturbed but not clean)",
        "",
    ]

    table_rows: dict[str, dict] = {}  # gate -> {sys: F1}
    for sys_name, pk, ext_map in systems:
        md += [f"## {sys_name}", "",
               "| Gate | TP | FP | FN | TN | P | R | F1 | N |",
               "|------|----|----|----|----|----|---|-----|---|"]
        gm = {}
        for gate in GATES:
            sub = [r for r in all_results if r["gate"] == gate]
            if not sub:
                continue
            labels = [r["label"] for r in sub]
            if ext_map is not None:
                preds = [ext_map.get(r["id"], -1) for r in sub]
            else:
                preds = [r.get(pk, -1) for r in sub]
            m = _metrics(labels, preds)
            gm[gate] = m
            skip = " *(skipped)*" if m["N"] == 0 else ""
            md.append(
                f"| {gate}{skip} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} "
                f"| {m['P']:.2f} | {m['R']:.2f} | {m['F1']:.2f} | {m['N']} |"
            )
            if gate not in table_rows:
                table_rows[gate] = {}
            table_rows[gate][sys_name] = m.get("F1", 0.0)
        valid = [v for v in gm.values() if v["N"] > 0]
        if valid:
            ap = sum(v["P"] for v in valid) / len(valid)
            ar = sum(v["R"] for v in valid) / len(valid)
            af = sum(v["F1"] for v in valid) / len(valid)
            md.append(f"| **Overall** | - | - | - | - "
                      f"| **{ap:.2f}** | **{ar:.2f}** | **{af:.2f}** | - |")
        md.append("")

    # Summary comparison table
    sys_names = [s[0] for s in systems]
    header = "| Gate | " + " | ".join(sys_names) + " |"
    sep    = "|------|" + "|".join(["------"]*len(sys_names)) + "|"
    md += ["## Summary: Macro F1 Comparison", "", header, sep]
    for gate in GATES:
        row_vals = [table_rows.get(gate, {}).get(s, None) for s in sys_names]
        cells = []
        for v in row_vals:
            if v is None:
                cells.append("skip")
            else:
                cells.append(f"**{v:.2f}**" if v == max(x for x in row_vals if x is not None) else f"{v:.2f}")
        md.append(f"| {gate} | " + " | ".join(cells) + " |")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\nReport saved: {OUT_MD}")
    print("\n" + "\n".join(md[-15:]))


if __name__ == "__main__":
    main()
