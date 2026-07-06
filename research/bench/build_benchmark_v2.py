"""Build a proper full-paper benchmark for ScholarLint.

Design principles:
1. FULL-PAPER mode: each case is a complete minimal LaTeX paper with all
   necessary components (tabular, bib, figures), not just a snippet.
2. CONTROLLED: we synthesise the papers so we know exactly what's there.
3. DIFFERENTIAL: pred = 1 iff gate(perturbed) > gate(clean).

Gates:
  A. data_integrity  -- NCG: claim in text vs table value
  B. citation        -- undefined \\cite{key}
  C. figure_crossref -- dangling \\ref{fig:x}

Perturbation types:
  P1  text_value_tamper   change value in text (table is ground truth)
  P2  table_value_tamper  change value in table (text stays)
  P3  cite_fake           add \\cite{fake_xyz} in text
  P4  cite_remove         break existing cite key in text
  P5  ref_dangling        add \\ref{fig:nonexistent} in text
  P6  label_missing       remove \\label from a figure

Output: research/bench/benchmark_v2.json

Run: python research/bench/build_benchmark_v2.py
"""

from __future__ import annotations
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = Path(__file__).parent / "benchmark_v2.json"
RNG  = random.Random(42)

# ─────────────────────────────────────────────────────────────────────────────
# Minimal LaTeX paper templates
# ─────────────────────────────────────────────────────────────────────────────

def _paper(body: str, bib: str = "") -> str:
    """Wrap body in a minimal LaTeX document with a bib section."""
    default_bib = r"""
@article{smith2024deep,
  author={Smith, John},
  title={Deep Learning Advances},
  journal={EMNLP},
  year={2024}
}
@article{jones2023bert,
  author={Jones, Alice},
  title={BERT Improvements},
  journal={ACL},
  year={2023}
}
@article{zhao2024llm,
  author={Zhao, Wei},
  title={Large Language Models},
  journal={NeurIPS},
  year={2024}
}
"""
    return (
        r"\documentclass{article}" + "\n"
        r"\usepackage[review]{acl}" + "\n"
        r"\begin{document}" + "\n"
        r"\section*{Limitations}" + "\n\n"
        + body + "\n"
        r"\bibliography{refs}" + "\n"
        r"\end{document}"
    ), (bib or default_bib)


# ─────────────────────────────────────────────────────────────────────────────
# Template pool: (description, clean_tex_body, bib)
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES = []

def _add(desc, body, bib=""):
    TEMPLATES.append({"desc": desc, "body": body, "bib": bib})


# T1: NLP paper with F1 scores
_add("nlp_f1_scores", r"""
\section{Introduction}
We propose \textbf{OurModel}, a novel approach to text classification.
Previous work \cite{smith2024deep} achieves an F1 of 85.2 on SST-2.
Our model achieves an F1 of 91.4 on SST-2 \cite{jones2023bert}.

\section{Experiments}
\begin{table}[h]
\caption{Main results on SST-2 and MNLI}
\label{tab:main}
\begin{tabular}{lcc}
\toprule
Model & F1 & Accuracy \\
\midrule
BERT & 85.2 & 84.6 \\
RoBERTa & 88.7 & 87.9 \\
OurModel & 91.4 & 90.8 \\
\bottomrule
\end{tabular}
\end{table}

As shown in Table~\ref{tab:main}, our model achieves an F1 of 91.4,
outperforming RoBERTa \cite{zhao2024llm} by 2.7 points.
The accuracy of our model is 90.8.
""")

# T2: CV paper with mAP scores
_add("cv_map_scores", r"""
\section{Introduction}
Object detection has advanced significantly \cite{smith2024deep}.
Our detector achieves a mAP of 54.3 on COCO \cite{jones2023bert}.

\section{Results}
\begin{table}[h]
\caption{Object detection results on COCO}
\label{tab:coco}
\begin{tabular}{lcc}
\toprule
Method & mAP & AP50 \\
\midrule
YOLO & 45.2 & 63.4 \\
DETR & 50.1 & 68.7 \\
Ours & 54.3 & 72.1 \\
\bottomrule
\end{tabular}
\end{table}

Figure~\ref{fig:architecture} shows our model architecture.
Our method achieves a mAP of 54.3, improving over DETR \cite{zhao2024llm} by 4.2.

\begin{figure}[h]
\centering
\caption{Model architecture overview}
\label{fig:architecture}
\end{figure}
""")

# T3: MT paper with BLEU scores
_add("mt_bleu_scores", r"""
\section{Introduction}
Neural machine translation \cite{smith2024deep} has seen rapid progress.
Our system achieves a BLEU of 32.8 on WMT14 En-De \cite{jones2023bert}.

\section{Experiments}
\begin{table}[h]
\caption{Translation results on WMT14 En-De}
\label{tab:mt}
\begin{tabular}{lc}
\toprule
System & BLEU \\
\midrule
Transformer & 28.4 \\
Ours (base) & 30.2 \\
Ours (large) & 32.8 \\
\bottomrule
\end{tabular}
\end{table}

As shown in Table~\ref{tab:mt}, our large model achieves BLEU of 32.8
on WMT14 \cite{zhao2024llm}, outperforming the standard Transformer by 4.4.
""")

# T4: QA paper with EM scores
_add("qa_em_scores", r"""
\section{Introduction}
Reading comprehension is a key NLP task \cite{smith2024deep}.
Our model achieves an exact match of 78.3 on SQuAD \cite{jones2023bert}.

\section{Results}
\begin{table}[h]
\caption{SQuAD v1.1 results}
\label{tab:squad}
\begin{tabular}{lcc}
\toprule
Model & EM & F1 \\
\midrule
BiDAF & 67.7 & 77.3 \\
BERT-base & 72.8 & 81.5 \\
Our model & 78.3 & 86.1 \\
\bottomrule
\end{tabular}
\end{table}

Our model achieves an exact match of 78.3 on SQuAD.
Figure~\ref{fig:results} shows learning curves.

\begin{figure}[h]
\centering
\caption{Learning curves on SQuAD}
\label{fig:results}
\end{figure}
""")

# T5: Summarization paper
_add("summarization_rouge", r"""
\section{Introduction}
Automatic summarization \cite{smith2024deep} is an important task.
We propose a new approach achieving ROUGE-L of 41.2 on CNN/DM \cite{jones2023bert}.

\section{Experiments}
\begin{table}[h]
\caption{Summarization results on CNN/DailyMail}
\label{tab:summ}
\begin{tabular}{lccc}
\toprule
Model & ROUGE-1 & ROUGE-2 & ROUGE-L \\
\midrule
PEGASUS & 43.9 & 21.1 & 40.9 \\
BART & 44.2 & 21.3 & 41.0 \\
Ours & 44.8 & 21.9 & 41.2 \\
\bottomrule
\end{tabular}
\end{table}

Our model achieves a ROUGE-L of 41.2 on CNN/DM \cite{zhao2024llm},
outperforming BART by 0.2 ROUGE-L points.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Perturbation functions  (operate on tex_body string)
# ─────────────────────────────────────────────────────────────────────────────

import re

def _perturb(v: str) -> str:
    """Return a plausibly-wrong numeric string."""
    f = float(v)
    dp = len(v.split(".")[1]) if "." in v else 0
    delta = RNG.choice([0.5, 1.0, 1.5, 2.0]) * (1 if dp == 1 else 0.1 if dp >= 2 else 1)
    sign = RNG.choice([-1, 1])
    new_f = round(f + sign * delta, dp)
    if new_f <= 0:
        new_f = round(f + delta, dp)
    return f"{new_f:.{dp}f}"


def apply_P1_text_tamper(body: str, tmpl: dict) -> tuple[str, dict]:
    """Change a numeric value in text prose (not in table rows)."""
    # Find numeric claims in prose lines
    pat = re.compile(r'(?:achieves?|obtains?|reaches?|improves?|outperforms?)[^.]{0,60}?(\d+\.\d+)', re.IGNORECASE)
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.count("&") >= 2:  # skip table rows
            continue
        m = pat.search(line)
        if m:
            orig = m.group(1)
            new = _perturb(orig)
            new_line = line[:m.start(1)] + new + line[m.end(1):]
            new_lines = lines[:]
            new_lines[i] = new_line
            return "\n".join(new_lines), {
                "type": "P1", "line": i+1,
                "original": orig, "modified": new,
                "context": line.strip()[:80]
            }
    return body, {}


def apply_P2_table_tamper(body: str, tmpl: dict) -> tuple[str, dict]:
    """Change a numeric value in a table row."""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.count("&") < 2:
            continue
        # Find numbers in this table row
        nums = re.findall(r'\d+\.\d+', line)
        if not nums:
            continue
        orig = nums[0]
        new = _perturb(orig)
        new_line = line.replace(orig, new, 1)
        new_lines = lines[:]
        new_lines[i] = new_line
        return "\n".join(new_lines), {
            "type": "P2", "line": i+1,
            "original": orig, "modified": new,
            "context": line.strip()[:80]
        }
    return body, {}


def apply_P3_cite_fake(body: str, tmpl: dict) -> tuple[str, dict]:
    """Add a fake \\cite{} key in text."""
    fake = "definitely_fake_key_xyz_2024"
    # Insert after first real \cite
    m = re.search(r'\\cite\{([^}]+)\}', body)
    if m:
        new_body = body[:m.end()] + f"\\cite{{{fake}}}" + body[m.end():]
        return new_body, {"type": "P3", "fake_key": fake, "line": body[:m.start()].count("\n")+1}
    return body, {}


def apply_P4_cite_remove(body: str, tmpl: dict) -> tuple[str, dict]:
    """Break an existing \\cite key (rename so it no longer exists in bib)."""
    m = re.search(r'\\cite\{([^}]+)\}', body)
    if m:
        orig_key = m.group(1).split(",")[0].strip()
        broken_key = orig_key + "_REMOVED"
        new_body = body.replace(f"{{{orig_key}}}", f"{{{broken_key}}}", 1)
        return new_body, {
            "type": "P4", "original_key": orig_key, "broken_key": broken_key,
            "line": body[:m.start()].count("\n")+1
        }
    return body, {}


def apply_P5_ref_dangling(body: str, tmpl: dict) -> tuple[str, dict]:
    """Add \\ref{} to a non-existent label."""
    fake_label = "fig:nonexistent_xyz_bench"
    # Find a prose line to inject into
    lines = body.split("\n")
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("\\") and not s.startswith("%") and len(s) > 20 and line.count("&") < 2:
            new_lines = lines[:]
            new_lines[i] = line.rstrip() + f" (see Figure~\\ref{{{fake_label}}})"
            return "\n".join(new_lines), {
                "type": "P5", "fake_label": fake_label, "line": i+1
            }
    return body, {}


def apply_P6_label_missing(body: str, tmpl: dict) -> tuple[str, dict]:
    """Remove a \\label{} from a figure, making \\ref point to nothing."""
    m = re.search(r'\\label\{(fig:[^}]+)\}', body)
    if m:
        label_key = m.group(1)
        new_body = body.replace(m.group(0), "", 1)
        return new_body, {
            "type": "P6", "removed_label": label_key,
            "line": body[:m.start()].count("\n")+1
        }
    return body, {}


PERTURBATIONS = {
    "data_integrity":          [apply_P1_text_tamper, apply_P2_table_tamper],
    "citation_bib_consistency":[apply_P3_cite_fake,   apply_P4_cite_remove],
    "figure_table_crossref":   [apply_P5_ref_dangling, apply_P6_label_missing],
}


# ─────────────────────────────────────────────────────────────────────────────
# Build cases
# ─────────────────────────────────────────────────────────────────────────────

def build():
    cases = []
    case_id = 0

    for tmpl in TEMPLATES:
        clean_body = tmpl["body"]
        clean_tex, bib_content = _paper(clean_body, tmpl.get("bib", ""))

        for gate, perturb_fns in PERTURBATIONS.items():
            for perturb_fn in perturb_fns:
                # PERTURBED case (label=1)
                perturbed_body, meta = perturb_fn(clean_body, tmpl)
                if not meta:
                    continue
                perturbed_tex, _ = _paper(perturbed_body, tmpl.get("bib", ""))
                cases.append({
                    "id": f"{tmpl['desc']}_{meta['type']}_{case_id}",
                    "template": tmpl["desc"],
                    "gate": gate,
                    "perturbation": meta["type"],
                    "label": 1,
                    "injected_at": meta,
                    "tex": perturbed_tex,
                    "bib": bib_content,
                    "clean_tex": clean_tex,
                })
                case_id += 1

                # CLEAN case (label=0) — one per perturbation type
                cases.append({
                    "id": f"{tmpl['desc']}_CLEAN_{gate}_{case_id}",
                    "template": tmpl["desc"],
                    "gate": gate,
                    "perturbation": "CLEAN",
                    "label": 0,
                    "injected_at": {},
                    "tex": clean_tex,
                    "bib": bib_content,
                    "clean_tex": clean_tex,
                })
                case_id += 1

    OUT.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_gate  = Counter(c["gate"] for c in cases)
    by_type  = Counter(c["perturbation"] for c in cases)
    by_label = Counter(c["label"] for c in cases)
    print(f"Wrote {len(cases)} cases to {OUT}")
    print(f"  gate:  {dict(by_gate)}")
    print(f"  perturb: {dict(by_type)}")
    print(f"  label 1={by_label[1]}  label 0={by_label[0]}")


if __name__ == "__main__":
    build()
