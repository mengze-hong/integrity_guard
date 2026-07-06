"""Build perturbation benchmark for ScholarLint gates.

Generates labeled test cases from real uploaded papers by injecting
controlled perturbations. Each case is either CLEAN (no injected bug)
or PERTURBED (injected bug of a specific type).

Gates evaluated:
  A. data_integrity  -- NCG: numerical claim vs table mismatch
  B. citation        -- undefined \cite{key}
  C. figure_crossref -- dangling \ref{fig:nonexistent}

Perturbation types:
  P1  value_swap      swap two numeric values in text (e.g. 75.3 → 74.3)
  P2  value_fabricate replace text value with plausible-but-wrong number
  P3  cite_fake       add \cite{definitely_fake_key_xyz} in text
  P4  ref_dangling    add \ref{fig:nonexistent_xyz} in text
  P5  cite_remove     remove a real bib entry so citation becomes undefined

Output: research/bench/benchmark.json
  [{
    "id": "0b1ba81e_P1_0",
    "paper": "0b1ba81e",
    "gate": "data_integrity",
    "perturbation": "P1",
    "label": 1,         # 1=bug present, 0=clean
    "tex_snippet": "...", # modified tex content (main file first 200 lines)
    "injected_at": {"line": 42, "original": "88.5", "modified": "87.3"},
    "clean_baseline": "..."  # same snippet without perturbation
  }]

Run:
    python research/bench/build_benchmark.py
"""

from __future__ import annotations

import copy
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPLOADS = ROOT / "uploads"
OUT = Path(__file__).parent / "benchmark.json"

# Papers to use: only the real non-template uploads
REAL_PAPERS = ["07c3d865f33e", "0b1ba81e", "316dd0a3", "4d44d6f4", "e237d467"]

# Use fixed seed for reproducibility
RNG = random.Random(42)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_main_tex(folder: Path) -> tuple[str, Path] | None:
    """Return (content, path) of the main .tex file."""
    candidates = sorted(folder.rglob("*.tex"))
    for p in candidates:
        text = p.read_text(encoding="utf-8", errors="replace")
        if r"\documentclass" in text and r"\begin{document}" in text:
            return text, p
    # fallback: largest tex file
    if candidates:
        p = max(candidates, key=lambda x: x.stat().st_size)
        return p.read_text(encoding="utf-8", errors="replace"), p
    return None


def _load_all_tex(folder: Path) -> list[tuple[str, Path]]:
    """Return all tex files."""
    return [(p.read_text(encoding="utf-8", errors="replace"), p)
            for p in sorted(folder.rglob("*.tex"))]


def _load_bib(folder: Path) -> list[str]:
    """Return list of bib keys from all .bib files."""
    keys = []
    for p in folder.rglob("*.bib"):
        for m in re.finditer(r"@\w+\s*\{([^,]+),", p.read_text(encoding="utf-8", errors="replace")):
            keys.append(m.group(1).strip())
    return keys


def _extract_numeric_claims(text: str) -> list[dict]:
    """Find lines with numeric claims (e.g. 'achieves F1 of 88.5')."""
    pat = re.compile(
        r"(?:achiev|obtain|reach|attain|report|score|get|improv|increas|reduc)\w*"
        r"(?:\s+\w+){0,4}?\s+(?:of\s+)?(\d+\.\d+)\s*(?:%|pp)?",
        re.IGNORECASE,
    )
    claims = []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        if s.startswith("%") or line.count("&") >= 2:
            continue
        for m in pat.finditer(line):
            claims.append({
                "line": lineno,
                "value_str": m.group(1),
                "value": float(m.group(1)),
                "context": line.strip()[:80],
            })
    return claims


def _find_cite_keys_in_text(text: str) -> list[tuple[int, str]]:
    """Return [(lineno, key), ...] of all \cite{key} in the text."""
    pat = re.compile(r"\\cite\w*\{([^}]+)\}")
    results = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("%"):
            continue
        for m in pat.finditer(line):
            for k in m.group(1).split(","):
                results.append((lineno, k.strip()))
    return results


def _find_label_keys(text: str) -> list[str]:
    """Return all \label{key} keys."""
    return re.findall(r"\\label\{([^}]+)\}", text)


def _find_ref_keys(text: str) -> list[str]:
    """Return all \ref{key} keys."""
    return re.findall(r"\\(?:ref|cref|autoref)\{([^}]+)\}", text)


def _perturb_value(v: float) -> str:
    """Return a plausibly-wrong version of a numeric value."""
    # ±1 to ±3 at the last decimal place, not too large a change
    dp = len(str(v).split(".")[1]) if "." in str(v) else 0
    delta = RNG.choice([1, 2, 3]) * (10 ** -dp)
    sign = RNG.choice([-1, 1])
    new_v = round(v + sign * delta, dp)
    if new_v <= 0:
        new_v = round(v + delta, dp)
    return f"{new_v:.{dp}f}"


# ─────────────────────────────────────────────────────────────────────────────
# Perturbation generators
# ─────────────────────────────────────────────────────────────────────────────

def gen_P1_value_swap(paper_id: str, text: str) -> list[dict]:
    """P1: swap a numeric value in text claim (text says X but table has Y)."""
    claims = _extract_numeric_claims(text)
    if not claims:
        return []
    cases = []
    sampled = RNG.sample(claims, min(3, len(claims)))
    lines = text.splitlines()
    for claim in sampled:
        new_val = _perturb_value(claim["value"])
        original = claim["value_str"]
        # Replace in that specific line
        modified_lines = lines[:]
        modified_lines[claim["line"] - 1] = modified_lines[claim["line"] - 1].replace(
            original, new_val, 1
        )
        modified_text = "\n".join(modified_lines)
        cases.append({
            "id": f"{paper_id}_P1_{claim['line']}",
            "paper": paper_id,
            "gate": "data_integrity",
            "perturbation": "P1",
            "label": 1,
            "injected_at": {
                "line": claim["line"],
                "original": original,
                "modified": new_val,
                "context": claim["context"],
            },
            "tex_snippet": _snippet(modified_text, claim["line"]),
            "clean_snippet": _snippet(text, claim["line"]),
        })
    return cases


def gen_P3_cite_fake(paper_id: str, text: str) -> list[dict]:
    """P3: inject a fake \cite{} key that doesn't exist in bib."""
    fake_key = f"definitely_fake_citation_xyz_{paper_id[:6]}"
    # Find a good insertion point: first \cite{} in text
    cite_lines = _find_cite_keys_in_text(text)
    if not cite_lines:
        return []
    insert_line, real_key = cite_lines[0]
    lines = text.splitlines()
    modified_lines = lines[:]
    # Insert fake cite right after the real one on that line
    modified_lines[insert_line - 1] = modified_lines[insert_line - 1].replace(
        f"\\cite{{{real_key}}}", f"\\cite{{{real_key}}}\\cite{{{fake_key}}}", 1
    )
    modified_text = "\n".join(modified_lines)
    return [{
        "id": f"{paper_id}_P3_0",
        "paper": paper_id,
        "gate": "citation_bib_consistency",
        "perturbation": "P3",
        "label": 1,
        "injected_at": {"line": insert_line, "fake_key": fake_key},
        "tex_snippet": _snippet(modified_text, insert_line),
        "clean_snippet": _snippet(text, insert_line),
    }]


def gen_P4_ref_dangling(paper_id: str, text: str) -> list[dict]:
    """P4: inject a \ref{} to a label that doesn't exist."""
    existing_labels = set(_find_label_keys(text))
    fake_label = f"fig:nonexistent_label_xyz_{paper_id[:6]}"
    # Find a sentence to inject into
    lines = text.splitlines()
    insert_line = None
    for i, line in enumerate(lines):
        s = line.strip()
        if (s and not s.startswith("%") and not s.startswith("\\")
                and len(s) > 20 and line.count("&") < 2):
            insert_line = i + 1
            break
    if insert_line is None:
        return []
    modified_lines = lines[:]
    modified_lines[insert_line - 1] += f" (see \\ref{{{fake_label}}})"
    modified_text = "\n".join(modified_lines)
    return [{
        "id": f"{paper_id}_P4_0",
        "paper": paper_id,
        "gate": "figure_table_crossref",
        "perturbation": "P4",
        "label": 1,
        "injected_at": {"line": insert_line, "fake_label": fake_label},
        "tex_snippet": _snippet(modified_text, insert_line),
        "clean_snippet": _snippet(text, insert_line),
    }]


def gen_P5_cite_remove(paper_id: str, text: str, bib_keys: list[str]) -> list[dict]:
    """P5: remove a real bib entry to make an existing cite undefined."""
    cite_lines = _find_cite_keys_in_text(text)
    used_keys = [k for _, k in cite_lines if k in bib_keys]
    if not used_keys:
        return []
    target_key = RNG.choice(used_keys)
    target_line = next(ln for ln, k in cite_lines if k == target_key)
    # We simulate this by relabelling the key in text to a different name
    broken_key = target_key + "_REMOVED"
    modified_text = text.replace(f"{{{target_key}}}", f"{{{broken_key}}}")
    return [{
        "id": f"{paper_id}_P5_0",
        "paper": paper_id,
        "gate": "citation_bib_consistency",
        "perturbation": "P5",
        "label": 1,
        "injected_at": {"line": target_line, "broken_key": broken_key, "original_key": target_key},
        "tex_snippet": _snippet(modified_text, target_line),
        "clean_snippet": _snippet(text, target_line),
    }]


def gen_clean(paper_id: str, text: str, gate: str, n: int = 2) -> list[dict]:
    """Clean baseline cases (label=0) for a gate."""
    lines = text.splitlines()
    # Pick n random mid-document lines
    mid = len(lines) // 2
    cases = []
    for i in range(n):
        pick = mid + i * 20
        cases.append({
            "id": f"{paper_id}_CLEAN_{gate}_{i}",
            "paper": paper_id,
            "gate": gate,
            "perturbation": "CLEAN",
            "label": 0,
            "injected_at": {},
            "tex_snippet": _snippet(text, pick),
            "clean_snippet": _snippet(text, pick),
        })
    return cases


def _snippet(text: str, center_line: int, context: int = 30) -> str:
    """Return ±context lines around center_line from text."""
    lines = text.splitlines()
    start = max(0, center_line - context - 1)
    end = min(len(lines), center_line + context)
    return "\n".join(lines[start:end])


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def build():
    cases = []
    for paper_id in REAL_PAPERS:
        folder = UPLOADS / paper_id
        if not folder.exists():
            print(f"  skip {paper_id} (not found)")
            continue

        result = _load_main_tex(folder)
        if not result:
            print(f"  skip {paper_id} (no main tex)")
            continue
        text, tex_path = result
        bib_keys = _load_bib(folder)

        print(f"{paper_id}: {len(text.splitlines())} lines, {len(bib_keys)} bib keys")

        # Generate perturbed cases
        cases.extend(gen_P1_value_swap(paper_id, text))
        cases.extend(gen_P3_cite_fake(paper_id, text))
        cases.extend(gen_P4_ref_dangling(paper_id, text))
        cases.extend(gen_P5_cite_remove(paper_id, text, bib_keys))

        # Generate clean baselines (2 per gate)
        for gate in ["data_integrity", "citation_bib_consistency", "figure_table_crossref"]:
            cases.extend(gen_clean(paper_id, text, gate, n=2))

    OUT.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(cases)} cases to {OUT}")

    # Summary
    from collections import Counter
    by_gate = Counter(c["gate"] for c in cases)
    by_perturb = Counter(c["perturbation"] for c in cases)
    by_label = Counter(c["label"] for c in cases)
    print(f"  by gate:        {dict(by_gate)}")
    print(f"  by perturbation:{dict(by_perturb)}")
    print(f"  label 1 (bug):  {by_label[1]}  label 0 (clean): {by_label[0]}")


if __name__ == "__main__":
    build()
