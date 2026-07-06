"""Run LLM baselines (B1) on benchmark_v2 using UXBench LLM client.

Models evaluated:
  - gpt-5.5       (OpenAI, reasoning)
  - claude-opus-4.7  (Anthropic)

Each model gets the full LaTeX snippet and must answer:
  {"bug": true/false, "reason": "..."}

Run:
    python research/bench/run_llm_baseline.py

Output: research/bench/eval_llm_baseline.json + eval_llm_baseline.md
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB  = Path(r"C:\Users\mengzehong\Desktop\UXBench\uxbench-v1.0\2_pipeline")
sys.path.insert(0, str(LIB))

from lib.llm_client import call_llm  # noqa: E402

BENCH   = Path(__file__).parent / "benchmark_v2.json"
OUT_JSON = Path(__file__).parent / "eval_llm_baseline.json"
OUT_MD   = Path(__file__).parent / "eval_llm_baseline.md"

MODELS = ["gpt-5.5", "claude-opus-4.7"]

# System prompt per gate
SYSTEM_PROMPTS = {
    "data_integrity": (
        "You are an academic integrity expert specializing in detecting data fabrication in papers. "
        "Given a LaTeX paper snippet, determine whether any numeric claim in the prose "
        "(outside of tables) contradicts the corresponding value in the tables. "
        "A 'bug' exists if a number stated in the text disagrees with the matching "
        "cell in the table (same metric, same model). "
        "Respond with ONLY a JSON object: {\"bug\": true/false, \"reason\": \"one sentence\"}"
    ),
    "citation_bib_consistency": (
        "You are an academic integrity expert. "
        "Given a LaTeX paper snippet, determine whether any \\cite{key} command references "
        "a citation key that is NOT defined in the bibliography section of this snippet. "
        "A 'bug' exists if there is an undefined citation key. "
        "Respond with ONLY a JSON object: {\"bug\": true/false, \"reason\": \"one sentence\"}"
    ),
    "figure_table_crossref": (
        "You are an academic integrity expert. "
        "Given a LaTeX paper snippet, determine whether any \\ref{label} command points to "
        "a label that is NOT defined by any \\label{} command in this snippet. "
        "A 'bug' exists if there is a dangling \\ref. "
        "Respond with ONLY a JSON object: {\"bug\": true/false, \"reason\": \"one sentence\"}"
    ),
}


def _predict_one(case: dict, model: str) -> int:
    """Return 1 if model thinks there's a bug, 0 otherwise."""
    system = SYSTEM_PROMPTS[case["gate"]]
    # Give the full perturbed paper (not snippet) — this is the real test
    user = f"LaTeX paper:\n```latex\n{case['tex'][:4000]}\n```"
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    result = call_llm(messages, model=model, max_tokens=300,
                      temperature=None if model.startswith("gpt-5") else 0.0)
    if not result.ok:
        print(f"    ERROR: {result.error}")
        return -1  # unknown
    raw = result.content or ""
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    try:
        data = json.loads(raw)
        return 1 if data.get("bug") else 0
    except Exception:
        # Try to extract true/false from text
        if re.search(r'"bug"\s*:\s*true', raw, re.IGNORECASE):
            return 1
        return 0


def _metrics(labels: list[int], preds: list[int]) -> dict:
    # Filter out unknown (-1)
    pairs = [(y, p) for y, p in zip(labels, preds) if p != -1]
    if not pairs:
        return {"TP": 0, "FP": 0, "FN": 0, "TN": 0, "P": 0, "R": 0, "F1": 0}
    labels_f, preds_f = zip(*pairs)
    tp = sum(1 for y, p in zip(labels_f, preds_f) if y == 1 and p == 1)
    fp = sum(1 for y, p in zip(labels_f, preds_f) if y == 0 and p == 1)
    fn = sum(1 for y, p in zip(labels_f, preds_f) if y == 1 and p == 0)
    tn = sum(1 for y, p in zip(labels_f, preds_f) if y == 0 and p == 0)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec  = tp / (tp + fn) if (tp + fn) else 0.0
    f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "P": round(prec, 3), "R": round(rec, 3), "F1": round(f1, 3),
            "N_valid": len(pairs)}


def run():
    cases = json.loads(BENCH.read_text(encoding="utf-8"))
    print(f"Loaded {len(cases)} cases")

    # Load existing results if any (resume support)
    existing = {}
    if OUT_JSON.exists():
        for r in json.loads(OUT_JSON.read_text(encoding="utf-8")):
            for m in MODELS:
                k = f"pred_{m}"
                if k in r and r[k] != -1:
                    existing[f"{r['id']}_{m}"] = r[k]
        print(f"Resuming: {len(existing)} predictions already cached")

    results = {c["id"]: dict(c) for c in cases}

    for model in MODELS:
        pred_key = f"pred_{model}"
        todo = [c for c in cases if existing.get(f"{c['id']}_{model}") is None]
        cached = len(cases) - len(todo)
        print(f"\n=== {model} === ({cached} cached, {len(todo)} to run)")

        # Restore cached
        for c in cases:
            k = f"{c['id']}_{model}"
            if k in existing:
                results[c["id"]][pred_key] = existing[k]

        # Run new ones with modest parallelism (avoid rate limits)
        def _task(case):
            pred = _predict_one(case, model)
            return case["id"], pred

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_task, c): c for c in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                cid, pred = fut.result()
                results[cid][pred_key] = pred
                label = results[cid]["label"]
                status = "TP" if (pred==1 and label==1) else \
                         "TN" if (pred==0 and label==0) else \
                         "FP" if (pred==1 and label==0) else \
                         "FN" if (pred==0 and label==1) else "ERR"
                print(f"  [{i}/{len(todo)}] {cid} -> {pred} [{status}]")
                # Save after each prediction for resume support
                OUT_JSON.write_text(
                    json.dumps(list(results.values()), indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )

    # ── Report ────────────────────────────────────────────────────────────────
    GATES = ["data_integrity", "citation_bib_consistency", "figure_table_crossref"]
    all_results = list(results.values())

    # Load Ours results for comparison
    ours_file = Path(__file__).parent / "eval_results_v2.json"
    ours_by_id = {}
    if ours_file.exists():
        for r in json.loads(ours_file.read_text(encoding="utf-8")):
            ours_by_id[r["id"]] = r.get("pred_ours")

    md = [
        "# ScholarLint LLM Baseline Evaluation",
        "",
        f"Benchmark: **benchmark_v2** ({len(cases)} cases, "
        f"bug={sum(1 for c in cases if c['label']==1)}, "
        f"clean={sum(1 for c in cases if c['label']==0)})",
        "",
        "Evaluation: full LaTeX paper → LLM binary classification (bug/no-bug)",
        "",
    ]

    all_metrics: dict[str, dict] = {}
    systems = [(m, f"pred_{m}") for m in MODELS]
    systems.append(("Ours (ScholarLint)", "pred_ours"))

    for sys_name, pk in systems:
        if pk == "pred_ours":
            preds_src = ours_by_id
            get_pred = lambda cid: preds_src.get(cid)
        else:
            get_pred = lambda cid, _pk=pk: results[cid].get(_pk)

        md += [f"## {sys_name}", "",
               "| Gate | TP | FP | FN | TN | P | R | F1 | N |",
               "|------|----|----|----|----|----|---|-----|---|"]
        gate_m = {}
        for gate in GATES:
            sub = [c for c in cases if c["gate"] == gate]
            labels = [c["label"] for c in sub]
            preds  = [get_pred(c["id"]) for c in sub]
            preds_clean = [p if p is not None else -1 for p in preds]
            m = _metrics(labels, preds_clean)
            gate_m[gate] = m
            md.append(
                f"| {gate} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} "
                f"| {m['P']:.2f} | {m['R']:.2f} | {m['F1']:.2f} | {m.get('N_valid','-')} |"
            )
        if gate_m:
            vals = [v for v in gate_m.values() if v.get("N_valid", 0) > 0]
            if vals:
                avg_p = sum(v["P"] for v in vals) / len(vals)
                avg_r = sum(v["R"] for v in vals) / len(vals)
                avg_f = sum(v["F1"] for v in vals) / len(vals)
                md.append(f"| **Overall** | - | - | - | - "
                           f"| **{avg_p:.2f}** | **{avg_r:.2f}** | **{avg_f:.2f}** | - |")
        md.append("")
        all_metrics[sys_name] = gate_m

    # Summary comparison table
    md += ["## Summary: Macro F1 Comparison", "",
           "| Gate | Ours | gpt-5.5 | claude-opus-4.7 |",
           "|------|------|---------|-----------------|"]
    for gate in GATES:
        def gf(name):
            v = all_metrics.get(name, {}).get(gate, {})
            f = v.get("F1")
            return f"{f:.2f}" if f is not None else "N/A"
        md.append(f"| {gate} | {gf('Ours (ScholarLint)')} "
                  f"| {gf('gpt-5.5')} | {gf('claude-opus-4.7')} |")
    md.append("")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\nReport saved to {OUT_MD}")
    print("\n" + "\n".join(md[-20:]))


if __name__ == "__main__":
    run()
