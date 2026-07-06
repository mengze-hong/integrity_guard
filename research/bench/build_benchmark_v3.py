"""Build ScholarLint benchmark v3.

Changes from v2:
- Remove P2 (baseline table tamper -- out of scope for claim-grounding)
- Remove writing_quality gate (not meaningful for rule-based benchmark)
- Add reference_authenticity gate: R1/R2/R3
- Add P1_xfile: cross-file NCG (body in main.tex, table in table.tex via \\input)
- More diverse templates (9 total)
- ~90 cases total

Gates:
  data_integrity          -- NCG claim vs table
  citation_bib_consistency -- undefined / broken cite keys
  figure_table_crossref   -- dangling ref / missing label
  reference_authenticity  -- fake DOI / title mismatch / author mismatch

Perturbation types:
  P1       text claim tampered (prose value changed, table stays)
  P1_xfile same as P1 but table is in a separate \\input{table.tex}
  P3       fake \\cite{} key injected
  P4       existing cite key broken (renamed)
  P5       dangling \\ref{fig:nonexistent}
  P6       \\label removed from figure
  R1       DOI replaced with plausible-but-nonexistent DOI
  R2       bib title tampered (real DOI, wrong title)
  R3       bib author count/name tampered (real DOI, wrong authors)

Run:  python research/bench/build_benchmark_v3.py
Out:  research/bench/benchmark_v3.json
"""

from __future__ import annotations
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT  = Path(__file__).parent / "benchmark_v3.json"
RNG  = random.Random(42)

# ─────────────────────────────────────────────────────────────────────────────
# Real DOIs used in reference gate cases (verified real papers)
# We use real DOIs so title/author data can be pulled from Crossref at eval time.
# Perturbations tamper with the .bib metadata, not the DOI itself (R2/R3) or
# replace the DOI with a fake one (R1).
# ─────────────────────────────────────────────────────────────────────────────

REAL_REFS = [
    {
        "key":     "vaswani2017attention",
        "doi":     "10.48550/arXiv.1706.03762",
        "title":   "Attention Is All You Need",
        "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar",
                    "Jakob Uszkoreit", "Llion Jones", "Aidan N. Gomez",
                    "Lukasz Kaiser", "Illia Polosukhin"],
        "year":    "2017",
        "journal": "NeurIPS",
    },
    {
        "key":     "devlin2019bert",
        "doi":     "10.18653/v1/N19-1423",
        "title":   "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
        "year":    "2019",
        "journal": "NAACL",
    },
    {
        "key":     "brown2020gpt3",
        "doi":     "10.48550/arXiv.2005.14165",
        "title":   "Language Models are Few-Shot Learners",
        "authors": ["Tom Brown", "Benjamin Mann", "Nick Ryder"],
        "year":    "2020",
        "journal": "NeurIPS",
    },
]


def _bib_entry(ref: dict) -> str:
    authors_bib = " and ".join(ref["authors"])
    return (
        f"@article{{{ref['key']},\n"
        f"  author = {{{authors_bib}}},\n"
        f"  title  = {{{ref['title']}}},\n"
        f"  doi    = {{{ref['doi']}}},\n"
        f"  year   = {{{ref['year']}}},\n"
        f"  journal = {{{ref['journal']}}}\n"
        f"}}"
    )


def _default_bib() -> str:
    return "\n\n".join(_bib_entry(r) for r in REAL_REFS) + "\n"


def _paper(body: str, extra_files: dict[str, str] | None = None,
           bib: str = "") -> tuple[str, str, dict[str, str]]:
    """Return (main_tex, bib_content, extra_files_dict)."""
    main = (
        r"\documentclass{article}" + "\n"
        r"\usepackage[review]{acl}" + "\n"
        r"\begin{document}" + "\n"
        r"\section*{Limitations}" + "\n\n"
        + body + "\n"
        r"\bibliography{refs}" + "\n"
        r"\end{document}"
    )
    return main, (bib or _default_bib()), (extra_files or {})


# ─────────────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: list[dict] = []

def _add(name: str, body: str, extra: dict[str, str] | None = None, bib: str = ""):
    TEMPLATES.append({"name": name, "body": body, "extra": extra or {}, "bib": bib})


# T1: NLP F1
_add("nlp_f1", r"""
\section{Introduction}
We propose \textbf{OurModel}, a text classifier \cite{devlin2019bert}.
Our model achieves an F1 of 91.4 on SST-2 \cite{vaswani2017attention}.

\section{Experiments}
\begin{table}[h]
\caption{Results on SST-2}
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

As shown in Table~\ref{tab:main}, OurModel achieves F1 of 91.4,
outperforming RoBERTa \cite{brown2020gpt3} by 2.7 points.
""")

# T2: CV mAP
_add("cv_map", r"""
\section{Introduction}
Object detection \cite{vaswani2017attention} has advanced rapidly.
Our detector achieves a mAP of 54.3 on COCO \cite{devlin2019bert}.

\section{Results}
\begin{table}[h]
\caption{Detection results on COCO}
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

Figure~\ref{fig:arch} illustrates the architecture \cite{brown2020gpt3}.
Ours achieves mAP of 54.3, improving over DETR by 4.2.

\begin{figure}[h]
\centering
\caption{Architecture overview}
\label{fig:arch}
\end{figure}
""")

# T3: MT BLEU
_add("mt_bleu", r"""
\section{Introduction}
Neural MT \cite{vaswani2017attention} achieves strong results.
Our system achieves BLEU of 32.8 on WMT14 En-De \cite{devlin2019bert}.

\section{Experiments}
\begin{table}[h]
\caption{WMT14 En-De results}
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

Our large model achieves BLEU of 32.8 \cite{brown2020gpt3}, outperforming
the Transformer by 4.4.
""")

# T4: QA exact-match
_add("qa_em", r"""
\section{Introduction}
Reading comprehension \cite{vaswani2017attention} is a core NLP task.
Our model achieves exact match of 78.3 on SQuAD \cite{devlin2019bert}.

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

Figure~\ref{fig:results} shows learning curves \cite{brown2020gpt3}.
Our model achieves exact match of 78.3 on SQuAD.

\begin{figure}[h]
\centering
\caption{Learning curves}
\label{fig:results}
\end{figure}
""")

# T5: Summarization ROUGE-L
_add("summ_rouge", r"""
\section{Introduction}
Summarization \cite{vaswani2017attention} is an important task.
We achieve ROUGE-L of 41.2 on CNN/DM \cite{devlin2019bert}.

\section{Experiments}
\begin{table}[h]
\caption{CNN/DailyMail results}
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

Our model achieves ROUGE-L of 41.2 on CNN/DM \cite{brown2020gpt3},
outperforming BART by 0.2.
""")

# T6: Cross-file table (P1_xfile test)
_add("xfile_f1",
     body=r"""
\section{Introduction}
We propose a new approach to text classification \cite{devlin2019bert}.
Our model achieves an F1 of 88.5 on MNLI \cite{vaswani2017attention}.

\section{Experiments}
\input{tab_results}

As shown in Table~\ref{tab:results}, our model achieves F1 of 88.5,
outperforming BERT \cite{brown2020gpt3} by 3.3 points.
""",
     extra={
         "tab_results.tex": r"""\begin{table}[h]
\caption{MNLI Results}
\label{tab:results}
\begin{tabular}{lcc}
\toprule
Model & F1 & Accuracy \\
\midrule
BERT & 85.2 & 84.3 \\
RoBERTa & 87.1 & 86.0 \\
Ours & 88.5 & 87.9 \\
\bottomrule
\end{tabular}
\end{table}
"""
     })

# T7: Multiple figures (P6 test)
_add("multi_fig", r"""
\section{Introduction}
We present a new method \cite{vaswani2017attention}.
Our model achieves accuracy of 93.2 on ImageNet \cite{devlin2019bert}.

\section{Method}
As shown in Figure~\ref{fig:overview}, our architecture has three components.
Figure~\ref{fig:ablation} shows ablation results \cite{brown2020gpt3}.

\begin{figure}[h]
\centering
\caption{System overview}
\label{fig:overview}
\end{figure}

\begin{figure}[h]
\centering
\caption{Ablation study}
\label{fig:ablation}
\end{figure}

\begin{table}[h]
\caption{ImageNet results}
\label{tab:imagenet}
\begin{tabular}{lc}
\toprule
Method & Accuracy \\
\midrule
ResNet-50 & 76.1 \\
ViT-B & 81.8 \\
Ours & 93.2 \\
\bottomrule
\end{tabular}
\end{table}
""")

# T8: Perplexity (language modeling)
_add("lm_ppl", r"""
\section{Introduction}
Language modeling \cite{vaswani2017attention} is foundational.
Our model achieves perplexity of 18.3 on WikiText-103 \cite{devlin2019bert}.

\section{Results}
\begin{table}[h]
\caption{WikiText-103 perplexity}
\label{tab:ppl}
\begin{tabular}{lc}
\toprule
Model & Perplexity \\
\midrule
GPT-2 & 29.4 \\
Transformer-XL & 21.8 \\
Ours & 18.3 \\
\bottomrule
\end{tabular}
\end{table}

Our model achieves perplexity of 18.3, improving over
Transformer-XL \cite{brown2020gpt3} by 3.5 points.
""")

# T9: Multi-table (tests that NCG picks the right table)
_add("multi_table", r"""
\section{Introduction}
We present results on two benchmarks \cite{vaswani2017attention}.
Our model achieves F1 of 82.1 on CoNLL-2003 \cite{devlin2019bert}.

\section{Results}

\begin{table}[h]
\caption{Dataset statistics}
\label{tab:stats}
\begin{tabular}{lcc}
\toprule
Dataset & Train & Test \\
\midrule
CoNLL-2003 & 14041 & 3684 \\
OntoNotes & 59924 & 8262 \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[h]
\caption{NER results on CoNLL-2003}
\label{tab:ner}
\begin{tabular}{lcc}
\toprule
Model & F1 & Precision \\
\midrule
BiLSTM-CRF & 71.1 & 70.8 \\
BERT-NER & 79.3 & 79.0 \\
Ours & 82.1 & 81.7 \\
\bottomrule
\end{tabular}
\end{table}

As shown in Table~\ref{tab:ner}, our model achieves F1 of 82.1
on CoNLL-2003 \cite{brown2020gpt3}.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Perturbation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _perturb_val(v: str) -> str:
    f = float(v)
    dp = len(v.split(".")[1]) if "." in v else 0
    delta = RNG.choice([0.5, 1.0, 1.5, 2.0]) * (1 if dp <= 1 else 0.1)
    sign  = RNG.choice([-1, 1])
    nf = round(f + sign * delta, dp)
    if nf <= 0:
        nf = round(f + abs(delta), dp)
    return f"{nf:.{dp}f}"


CLAIM_PAT = re.compile(
    r"(?:achieves?|obtains?|reaches?|improves?|outperforms?)[^.\n]{0,80}?(\d+\.\d+)",
    re.IGNORECASE,
)
TABLE_NUM_PAT = re.compile(r"(\d+\.\d+)")


def _apply_P1(body: str) -> tuple[str, dict]:
    """Change a numeric value in prose (not table rows)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.count("&") >= 2:
            continue
        m = CLAIM_PAT.search(line)
        if m:
            orig = m.group(1)
            new  = _perturb_val(orig)
            lines[i] = line[:m.start(1)] + new + line[m.end(1):]
            return "\n".join(lines), {
                "type": "P1", "line": i + 1,
                "original": orig, "modified": new,
                "context": line.strip()[:80],
            }
    return body, {}


def _apply_P1_xfile(body: str, extra: dict[str, str]) -> tuple[str, dict, dict[str, str]]:
    """Change a numeric value in prose; table lives in a separate file."""
    new_body, meta = _apply_P1(body)
    return new_body, meta, extra  # extra files unchanged (table correct)


def _apply_P3(body: str) -> tuple[str, dict]:
    """Inject a fake \\cite{} key."""
    fake = "llm_hallucinated_fake_citation_2024"
    m = re.search(r"\\cite\{([^}]+)\}", body)
    if m:
        new_body = body[:m.end()] + f"\\cite{{{fake}}}" + body[m.end():]
        return new_body, {"type": "P3", "fake_key": fake,
                          "line": body[:m.start()].count("\n") + 1}
    return body, {}


def _apply_P4(body: str) -> tuple[str, dict]:
    """Break an existing cite key."""
    m = re.search(r"\\cite\{([^}]+)\}", body)
    if m:
        orig = m.group(1).split(",")[0].strip()
        broken = orig + "_REMOVED"
        new_body = body.replace(f"{{{orig}}}", f"{{{broken}}}", 1)
        return new_body, {
            "type": "P4", "original_key": orig, "broken_key": broken,
            "line": body[:m.start()].count("\n") + 1,
        }
    return body, {}


def _apply_P5(body: str) -> tuple[str, dict]:
    """Add dangling \\ref{}."""
    fake = "fig:nonexistent_xyz_bench_2024"
    lines = body.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("\\") and not s.startswith("%") \
                and len(s) > 20 and line.count("&") < 2:
            lines[i] = line.rstrip() + f" (Figure~\\ref{{{fake}}})"
            return "\n".join(lines), {"type": "P5", "fake_label": fake, "line": i + 1}
    return body, {}


def _apply_P6(body: str) -> tuple[str, dict]:
    """Remove a \\label{} from a figure."""
    m = re.search(r"\\label\{(fig:[^}]+)\}", body)
    if m:
        key = m.group(1)
        new_body = body.replace(m.group(0), "", 1)
        return new_body, {
            "type": "P6", "removed_label": key,
            "line": body[:m.start()].count("\n") + 1,
        }
    return body, {}


# ── Reference perturbations ──────────────────────────────────────────────────

def _apply_R1(bib: str, ref: dict) -> tuple[str, dict]:
    """Replace a real DOI with a plausible-but-nonexistent fake DOI."""
    fake_doi = f"10.99999/fakejour.{RNG.randint(10000, 99999)}.{RNG.randint(100, 999)}"
    new_bib = bib.replace(ref["doi"], fake_doi, 1)
    return new_bib, {"type": "R1", "original_doi": ref["doi"],
                     "fake_doi": fake_doi, "key": ref["key"]}


def _apply_R2(bib: str, ref: dict) -> tuple[str, dict]:
    """Keep real DOI but change the bib title to something plausible-but-wrong."""
    fake_title = ref["title"] + " Revisited: A New Perspective"
    new_bib = bib.replace(ref["title"], fake_title, 1)
    return new_bib, {"type": "R2", "original_title": ref["title"],
                     "fake_title": fake_title, "key": ref["key"]}


def _apply_R3(bib: str, ref: dict) -> tuple[str, dict]:
    """Keep real DOI but add a fake extra author."""
    orig_authors = " and ".join(ref["authors"])
    fake_author  = "John Q. Fabricated"
    new_authors  = orig_authors + f" and {fake_author}"
    new_bib = bib.replace(orig_authors, new_authors, 1)
    return new_bib, {"type": "R3", "key": ref["key"],
                     "original_authors": orig_authors, "fake_author": fake_author}


# ─────────────────────────────────────────────────────────────────────────────
# Case builder
# ─────────────────────────────────────────────────────────────────────────────

def _case(cid: str, tmpl_name: str, gate: str, perturb: str, label: int,
          tex: str, bib: str, clean_tex: str, clean_bib: str,
          extra_files: dict, clean_extra: dict, meta: dict) -> dict:
    return {
        "id": cid, "template": tmpl_name, "gate": gate,
        "perturbation": perturb, "label": label,
        "injected_at": meta,
        "tex": tex, "bib": bib,
        "clean_tex": clean_tex, "clean_bib": clean_bib,
        "extra_files": extra_files,
        "clean_extra_files": clean_extra,
    }


def build():
    cases: list[dict] = []
    _id = 0

    for tmpl in TEMPLATES:
        clean_tex, clean_bib, clean_extra = _paper(
            tmpl["body"], tmpl["extra"], tmpl.get("bib", "")
        )

        def mk(gate, perturb, ptex, pbib, meta, pextra=None):
            nonlocal _id
            cid = f"{tmpl['name']}_{perturb}_{_id}"
            _id += 1
            cases.append(_case(
                cid, tmpl["name"], gate, perturb, 1,
                ptex, pbib, clean_tex, clean_bib,
                pextra or clean_extra, clean_extra, meta
            ))
            # Paired CLEAN case
            cid2 = f"{tmpl['name']}_CLEAN_{gate}_{_id}"
            _id += 1
            cases.append(_case(
                cid2, tmpl["name"], gate, "CLEAN", 0,
                clean_tex, clean_bib, clean_tex, clean_bib,
                clean_extra, clean_extra, {}
            ))

        # ── data_integrity ────────────────────────────────────────────────
        body_p1, meta_p1 = _apply_P1(tmpl["body"])
        if meta_p1:
            tex_p1, bib_p1, _ = _paper(body_p1, tmpl["extra"], tmpl.get("bib", ""))
            mk("data_integrity", "P1", tex_p1, bib_p1, meta_p1)

        # Cross-file P1 only for xfile template
        if tmpl["name"] == "xfile_f1" and meta_p1:
            body_p1x, meta_p1x = _apply_P1(tmpl["body"])
            if meta_p1x:
                tex_p1x, bib_p1x, _ = _paper(body_p1x, tmpl["extra"], tmpl.get("bib", ""))
                meta_p1x["type"] = "P1_xfile"
                nonlocal_id = _id
                cid = f"{tmpl['name']}_P1_xfile_{_id}"
                _id += 1
                cases.append(_case(
                    cid, tmpl["name"], "data_integrity", "P1_xfile", 1,
                    tex_p1x, bib_p1x, clean_tex, clean_bib,
                    tmpl["extra"], clean_extra, meta_p1x
                ))
                cid2 = f"{tmpl['name']}_CLEAN_data_integrity_{_id}"
                _id += 1
                cases.append(_case(
                    cid2, tmpl["name"], "data_integrity", "CLEAN", 0,
                    clean_tex, clean_bib, clean_tex, clean_bib,
                    clean_extra, clean_extra, {}
                ))

        # ── citation_bib_consistency ──────────────────────────────────────
        body_p3, meta_p3 = _apply_P3(tmpl["body"])
        if meta_p3:
            tex_p3, bib_p3, _ = _paper(body_p3, tmpl["extra"], tmpl.get("bib", ""))
            mk("citation_bib_consistency", "P3", tex_p3, bib_p3, meta_p3)

        body_p4, meta_p4 = _apply_P4(tmpl["body"])
        if meta_p4:
            tex_p4, bib_p4, _ = _paper(body_p4, tmpl["extra"], tmpl.get("bib", ""))
            mk("citation_bib_consistency", "P4", tex_p4, bib_p4, meta_p4)

        # ── figure_table_crossref ─────────────────────────────────────────
        body_p5, meta_p5 = _apply_P5(tmpl["body"])
        if meta_p5:
            tex_p5, bib_p5, _ = _paper(body_p5, tmpl["extra"], tmpl.get("bib", ""))
            mk("figure_table_crossref", "P5", tex_p5, bib_p5, meta_p5)

        body_p6, meta_p6 = _apply_P6(tmpl["body"])
        if meta_p6:
            tex_p6, bib_p6, _ = _paper(body_p6, tmpl["extra"], tmpl.get("bib", ""))
            mk("figure_table_crossref", "P6", tex_p6, bib_p6, meta_p6)

        # ── reference_authenticity ────────────────────────────────────────
        # Use the first real ref for each template
        ref = RNG.choice(REAL_REFS)
        bib_r1, meta_r1 = _apply_R1(clean_bib, ref)
        if meta_r1:
            mk("reference_authenticity", "R1", clean_tex, bib_r1, meta_r1)

        bib_r2, meta_r2 = _apply_R2(clean_bib, ref)
        if meta_r2:
            mk("reference_authenticity", "R2", clean_tex, bib_r2, meta_r2)

        bib_r3, meta_r3 = _apply_R3(clean_bib, ref)
        if meta_r3:
            mk("reference_authenticity", "R3", clean_tex, bib_r3, meta_r3)

    OUT.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_gate  = Counter(c["gate"]         for c in cases)
    by_perturb = Counter(c["perturbation"] for c in cases)
    by_label = Counter(c["label"]         for c in cases)
    print(f"Wrote {len(cases)} cases to {OUT}")
    print(f"  gate:      {dict(sorted(by_gate.items()))}")
    print(f"  perturb:   {dict(sorted(by_perturb.items()))}")
    print(f"  label 1={by_label[1]}  label 0={by_label[0]}")


if __name__ == "__main__":
    build()
