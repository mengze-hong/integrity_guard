"""Build ScholarLint MULTI-ISSUE benchmark.

Hypothesis under test: real papers contain MANY integrity issues at once.
A method that reads the whole source and is asked to "find all problems"
should be judged on how many of the injected issues it recovers — not on a
single yes/no per gate.

Each benchmark paper here has K distinct issues injected across all four
gates (data / citation / figure / reference). Every injected issue carries a
matchable ground-truth *signature* (a cite key, a ref label, a bib key, or a
numeric value) so both ScholarLint and an LLM baseline can be scored against
the same ground truth, and so a later human baseline uses the identical keys.

Reuses the 14 templates, real DOIs, and perturbation functions from
build_benchmark_v3.py (imported, not duplicated).

Run:  python research/bench/build_benchmark_multi.py
Out:  research/bench/benchmark_multi.json
"""

from __future__ import annotations
import json
import random
import re
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from build_benchmark_v3 import (  # noqa: E402
    TEMPLATES, REAL_REFS, _wrap, _bib_block,
    apply_P1, apply_P3, apply_P4, apply_P5, apply_P6,
    apply_R1, apply_R2, apply_R3,
)

OUT = _HERE / "benchmark_multi.json"

# How many randomized variants to emit per template. Variant 0 injects the
# full applicable set (max issues); later variants inject random subsets so
# papers vary in issue count, closer to real life.
VARIANTS_PER_TEMPLATE = 3
SUBSET_MIN, SUBSET_MAX = 4, 8


# ─────────────────────────────────────────────────────────────────────────────
# Ground-truth signature: normalise each perturbation's meta into a matchable
# record. `key` is the single string an evaluator matches on (case-insensitive
# substring), plus a human-readable `detail`.
# ─────────────────────────────────────────────────────────────────────────────

def _signature(meta: dict) -> dict | None:
    t = meta.get("type")
    if t in ("P1", "P1_xfile"):
        return {"gate": "data_integrity", "type": "data_claim_mismatch",
                "key": meta["modified"],  # the wrong number appearing in prose
                "detail": f"prose claims {meta['modified']} but table has {meta['original']}"}
    if t == "P3":
        return {"gate": "citation_bib_consistency", "type": "undefined_citation",
                "key": meta["fake_key"],
                "detail": f"\\cite{{{meta['fake_key']}}} has no .bib entry"}
    if t == "P4":
        return {"gate": "citation_bib_consistency", "type": "undefined_citation",
                "key": meta["broken_key"],
                "detail": f"\\cite{{{meta['broken_key']}}} has no .bib entry (typo)"}
    if t == "P5":
        return {"gate": "figure_table_crossref", "type": "dangling_ref",
                "key": meta["fake_label"],
                "detail": f"\\ref{{{meta['fake_label']}}} has no \\label"}
    if t == "P6":
        return {"gate": "figure_table_crossref", "type": "dangling_ref",
                "key": meta["removed_label"],
                "detail": f"\\label{{{meta['removed_label']}}} removed; its \\ref now dangles"}
    if t == "R1":
        return {"gate": "reference_authenticity", "type": "invalid_doi",
                "key": meta["key"],
                "detail": f"reference '{meta['key']}' has an unresolvable/fake DOI"}
    if t == "R2":
        return {"gate": "reference_authenticity", "type": "title_mismatch",
                "key": meta["key"],
                "detail": f"reference '{meta['key']}' title does not match its DOI"}
    if t == "R3":
        return {"gate": "reference_authenticity", "type": "author_mismatch",
                "key": meta["key"],
                "detail": f"reference '{meta['key']}' has a fabricated extra author"}
    return None


def _inject(clean_body: str, clean_bib: str, extra: dict, cited_refs: list[dict],
            chosen: list[str], rng: random.Random) -> tuple[str, str, dict, list[dict]]:
    """Apply the chosen perturbation types to a cleaned template.

    Returns (tex, bib, extra_files, ground_truth_issues).
    Body perturbations are applied in a collision-safe order; reference
    perturbations target distinct CITED refs.
    """
    body = clean_body
    issues: list[dict] = []

    # Body order: P6 (remove label) -> P5 (add dangling ref) -> P4 (break cite)
    # -> P3 (insert fake cite) -> P1 (tamper number). Each touches a different
    # construct so they don't clobber one another.
    for pt in ["P6", "P5", "P4", "P3", "P1"]:
        if pt not in chosen:
            continue
        fn = {"P6": apply_P6, "P5": apply_P5, "P4": apply_P4,
              "P3": apply_P3, "P1": apply_P1}[pt]
        new_body, meta = fn(body)
        if meta:
            body = new_body
            sig = _signature(meta)
            if sig:
                issues.append(sig)

    # Reference perturbations on DISTINCT cited refs so they don't overwrite.
    bib = clean_bib
    ref_types = [rt for rt in ["R1", "R2", "R3"] if rt in chosen]
    if ref_types and cited_refs:
        refs = rng.sample(cited_refs, k=min(len(ref_types), len(cited_refs)))
        for rt, ref in zip(ref_types, refs):
            fn = {"R1": apply_R1, "R2": apply_R2, "R3": apply_R3}[rt]
            new_bib, meta = fn(bib, ref)
            if meta:
                bib = new_bib
                sig = _signature(meta)
                if sig:
                    issues.append(sig)

    tex, _, ex = _wrap(body, extra, clean_bib)
    return tex, bib, ex, issues


ALL_TYPES = ["P1", "P3", "P4", "P5", "P6", "R1", "R2", "R3"]


# ─────────────────────────────────────────────────────────────────────────────
# Make a template genuinely CLEAN so that, post-injection, the only issues in a
# paper are the injected ones (any extra flag is then a true false positive).
#   * bib holds ONLY the refs actually cited (no orphan-entry warnings)
#   * every table/figure \label (incl. cross-file) is \ref'd in the prose
# ─────────────────────────────────────────────────────────────────────────────

def _cited_keys(body: str) -> list[str]:
    keys: list[str] = []
    for grp in re.findall(r"\\cite[tp]?\{([^}]+)\}", body):
        for k in grp.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


def _cited_refs(body: str) -> list[dict]:
    cited = set(_cited_keys(body))
    return [r for r in REAL_REFS if r["key"] in cited]


def _ensure_float_refs(body: str, extra: dict) -> str:
    """Append a benign reference for any table/figure label not already \\ref'd."""
    all_text = body + "\n" + "\n".join(extra.values())
    labels = re.findall(r"\\label\{((?:tab|fig):[^}]+)\}", all_text)
    add_lines = []
    for lab in labels:
        if f"\\ref{{{lab}}}" not in body:
            kind = "Table" if lab.startswith("tab:") else "Figure"
            add_lines.append(f"{kind}~\\ref{{{lab}}} summarises these results.")
    if add_lines:
        body = body.rstrip() + "\n" + " ".join(add_lines) + "\n"
    return body


def _clean_template(tmpl: dict) -> tuple[str, str, dict]:
    """Return (clean_body, trimmed_bib, extra) with no orphan refs / unused floats."""
    body = _ensure_float_refs(tmpl["body"], tmpl.get("extra", {}))
    refs = _cited_refs(body)
    bib = _bib_block(refs) if refs else ""
    return body, bib, tmpl.get("extra", {})


def build():
    rng = random.Random(1234)
    papers: list[dict] = []

    for tmpl in TEMPLATES:
        clean_body, trimmed_bib, extra = _clean_template(tmpl)
        cited_refs = _cited_refs(clean_body)
        clean_tex, clean_bib, clean_extra = _wrap(clean_body, extra, trimmed_bib)

        # One CLEAN paper per template (0 injected issues) for precision / FP.
        papers.append({
            "id": f"{tmpl['name']}_clean",
            "template": tmpl["name"],
            "label": "clean",
            "tex": clean_tex, "bib": clean_bib, "extra_files": clean_extra,
            "issues": [],
        })

        for v in range(VARIANTS_PER_TEMPLATE):
            if v == 0:
                chosen = list(ALL_TYPES)  # maximal
            else:
                k = rng.randint(SUBSET_MIN, SUBSET_MAX)
                chosen = rng.sample(ALL_TYPES, k=k)
            tex, bib, ex, issues = _inject(clean_body, trimmed_bib, extra,
                                           cited_refs, chosen, rng)
            for j, iss in enumerate(issues):
                iss["issue_id"] = f"{tmpl['name']}_v{v}_i{j}"
            papers.append({
                "id": f"{tmpl['name']}_v{v}",
                "template": tmpl["name"],
                "label": "buggy",
                "tex": tex, "bib": bib, "extra_files": ex,
                "issues": issues,
            })

    OUT.write_text(json.dumps(papers, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    buggy = [p for p in papers if p["label"] == "buggy"]
    clean = [p for p in papers if p["label"] == "clean"]
    total_issues = sum(len(p["issues"]) for p in papers)
    by_gate = Counter(i["gate"] for p in papers for i in p["issues"])
    by_type = Counter(i["type"] for p in papers for i in p["issues"])
    counts = [len(p["issues"]) for p in buggy]
    print(f"Wrote {len(papers)} papers to {OUT}")
    print(f"  buggy={len(buggy)}  clean={len(clean)}")
    print(f"  total injected issues: {total_issues}")
    print(f"  issues/buggy paper: min={min(counts)} max={max(counts)} mean={sum(counts)/len(counts):.1f}")
    print(f"  by gate: {dict(sorted(by_gate.items()))}")
    print(f"  by type: {dict(sorted(by_type.items()))}")


if __name__ == "__main__":
    build()
