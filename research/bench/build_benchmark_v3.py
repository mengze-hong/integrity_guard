"""Build ScholarLint benchmark v3 (solid version).

Design goals:
1. 200+ cases, balanced (bug/clean)
2. Realistic: real ACL/EMNLP DOIs with full Crossref metadata
3. Diverse: 14 paper templates across NLP/CV/ML
4. Coverage: 4 gates, 9 perturbation types
5. No P2 (out of scope), no writing gate

Gates & perturbations:
  data_integrity       P1 (text claim tampered)
                       P1_xfile (cross-file table)
  citation             P3 (fake cite key injected)
                       P4 (existing key broken)
  figure_crossref      P5 (dangling ref)
                       P6 (label removed)
  reference_auth       R1 (fake DOI, plausible format)
                       R2 (real DOI, title tampered)
                       R3 (real DOI, author count/name tampered)

Real DOIs used (all have full Crossref title+author metadata):
  BART      10.18653/v1/2020.acl-main.703
  PGNet     10.18653/v1/P17-1099
  Parrots   10.1145/3442188.3445922
  EMNLP22   10.18653/v1/2022.emnlp-main.1
  NAACL21   10.18653/v1/2021.naacl-main.10
  PrefixTune 10.18653/v1/2021.acl-long.353

Run:  python research/bench/build_benchmark_v3.py
Out:  research/bench/benchmark_v3.json
"""

from __future__ import annotations
import json
import random
import re
from pathlib import Path

RNG = random.Random(42)
OUT = Path(__file__).parent / "benchmark_v3.json"

# ─────────────────────────────────────────────────────────────────────────────
# Real reference pool — all have Crossref title+authors
# ─────────────────────────────────────────────────────────────────────────────
REAL_REFS = [
    {
        "key": "lewis2020bart",
        "doi": "10.18653/v1/2020.acl-main.703",
        "title": "BART: Denoising Sequence-to-Sequence Pre-training for Natural Language Generation, Translation, and Comprehension",
        "authors": ["Mike Lewis", "Yinhan Liu", "Naman Goyal", "Marjan Ghazvininejad",
                    "Abdelrahman Mohamed", "Omer Levy", "Veselin Stoyanov", "Luke Zettlemoyer"],
        "year": "2020", "venue": "ACL",
    },
    {
        "key": "see2017get",
        "doi": "10.18653/v1/P17-1099",
        "title": "Get To The Point: Summarization with Pointer-Generator Networks",
        "authors": ["Abigail See", "Peter J. Liu", "Christopher D. Manning"],
        "year": "2017", "venue": "ACL",
    },
    {
        "key": "bender2021parrots",
        "doi": "10.1145/3442188.3445922",
        "title": "On the Dangers of Stochastic Parrots",
        "authors": ["Emily M. Bender", "Timnit Gebru", "Angelina McMillan-Major", "Shmargaret Shmitchell"],
        "year": "2021", "venue": "FAccT",
    },
    {
        "key": "ye2022generative",
        "doi": "10.18653/v1/2022.emnlp-main.1",
        "title": "Generative Knowledge Graph Construction: A Review",
        "authors": ["Hongbin Ye", "Ningyu Zhang", "Hui Chen", "Huajun Chen"],
        "year": "2022", "venue": "EMNLP",
    },
    {
        "key": "rogers2020primer",
        "doi": "10.1162/tacl_a_00349",
        "title": "A Primer in BERTology: What We Know About How BERT Works",
        "authors": ["Anna Rogers", "Olga Kovaleva", "Anna Rumshisky"],
        "year": "2020", "venue": "TACL",
    },
    {
        "key": "li2021prefix",
        "doi": "10.18653/v1/2021.acl-long.353",
        "title": "Prefix-Tuning: Optimizing Continuous Prompts for Generation",
        "authors": ["Xiang Lisa Li", "Percy Liang"],
        "year": "2021", "venue": "ACL",
    },
]

def _bib_block(refs: list[dict]) -> str:
    parts = []
    for r in refs:
        authors_str = " and ".join(r["authors"])
        parts.append(
            f"@inproceedings{{{r['key']},\n"
            f"  author  = {{{authors_str}}},\n"
            f"  title   = {{{r['title']}}},\n"
            f"  doi     = {{{r['doi']}}},\n"
            f"  year    = {{{r['year']}}},\n"
            f"  booktitle = {{{r['venue']}}}\n"
            f"}}"
        )
    return "\n\n".join(parts)

DEFAULT_BIB = _bib_block(REAL_REFS)

def _wrap(body: str, extra_files: dict | None = None, bib: str = "") -> tuple[str, str, dict]:
    main = (
        r"\documentclass{article}" + "\n"
        r"\usepackage[review]{acl}" + "\n"
        r"\begin{document}" + "\n"
        r"\section*{Limitations}" + "\n\n"
        + body.strip() + "\n\n"
        r"\bibliography{refs}" + "\n"
        r"\end{document}"
    )
    return main, bib or DEFAULT_BIB, extra_files or {}


# ─────────────────────────────────────────────────────────────────────────────
# Paper templates — 14 diverse NLP/ML scenarios
# Every template cites at least 2 real refs, has a proper results table,
# at least one figure with label+ref, and prose claims matching table values.
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: list[dict] = []

def T(name: str, body: str, extra: dict | None = None, bib: str = ""):
    TEMPLATES.append({"name": name, "body": body, "extra": extra or {}, "bib": bib})


# ── T01: Text classification F1 ──────────────────────────────────────────────
T("t01_clf_f1", r"""
\section{Introduction}
Text classification is a fundamental NLP task.
Following \citet{lewis2020bart} and \citet{li2021prefix}, we propose OurModel.
Our model achieves an F1 of 91.4 on SST-2.

\section{Model}
Figure~\ref{fig:arch} illustrates our architecture.
\begin{figure}[h]\centering\caption{Architecture.}\label{fig:arch}\end{figure}

\section{Experiments}
\begin{table}[h]
\caption{SST-2 results.}
\label{tab:sst2}
\begin{tabular}{lcc}
\toprule
Model & F1 & Acc \\
\midrule
BERT & 85.2 & 84.6 \\
RoBERTa & 88.7 & 87.9 \\
OurModel & 91.4 & 90.8 \\
\bottomrule
\end{tabular}
\end{table}
OurModel achieves F1 of 91.4, improving over RoBERTa \citep{see2017get} by 2.7 pts.
""")

# ── T02: NER CoNLL-2003 ───────────────────────────────────────────────────────
T("t02_ner_conll", r"""
\section{Introduction}
Named entity recognition (NER) is crucial for IE.
\citet{li2021prefix} propose prefix-tuning; we adapt it for NER.
Our system achieves F1 of 93.5 on CoNLL-2003 \citep{lewis2020bart}.

\section{Experiments}
\begin{table}[h]
\caption{CoNLL-2003 NER results.}
\label{tab:ner}
\begin{tabular}{lcc}
\toprule
Model & F1 & Prec \\
\midrule
BiLSTM-CRF & 86.1 & 85.3 \\
BERT-NER & 92.8 & 92.0 \\
Ours & 93.5 & 92.7 \\
\bottomrule
\end{tabular}
\end{table}
Figure~\ref{fig:ner_curve} shows learning curves.
\begin{figure}[h]\centering\caption{NER learning curves.}\label{fig:ner_curve}\end{figure}
Ours achieves F1 of 93.5, a new SOTA on CoNLL-2003.
""")

# ── T03: MT BLEU (WMT14 En-De) ────────────────────────────────────────────────
T("t03_mt_bleu", r"""
\section{Introduction}
Neural MT has seen rapid progress \citep{lewis2020bart}.
We build on \citet{see2017get} for our encoder design.
Our large model achieves BLEU of 32.8 on WMT14 En-De.

\section{Experiments}
\begin{table}[h]
\caption{WMT14 En-De translation results.}
\label{tab:mt}
\begin{tabular}{lcc}
\toprule
System & BLEU & BLEU-4 \\
\midrule
Transformer & 27.3 & 28.4 \\
Ours-base & 29.6 & 30.2 \\
Ours-large & 31.4 & 32.8 \\
\bottomrule
\end{tabular}
\end{table}
As shown in Table~\ref{tab:mt}, our large model achieves BLEU of 32.8,
outperforming the Transformer \citep{bender2021parrots} by 4.4 pts.
Figure~\ref{fig:bleu_curve} shows BLEU vs model size.
\begin{figure}[h]\centering\caption{BLEU vs model size.}\label{fig:bleu_curve}\end{figure}
""")

# ── T04: Extractive QA (SQuAD EM) ────────────────────────────────────────────
T("t04_qa_squad", r"""
\section{Introduction}
Extractive QA on SQuAD v1.1 is a standard benchmark \citep{li2021prefix}.
Our model achieves exact match of 78.3 on SQuAD.

\section{Experiments}
\begin{table}[h]
\caption{SQuAD v1.1 results.}
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
Figure~\ref{fig:qa_attn} visualises attention patterns \citep{see2017get}.
\begin{figure}[h]\centering\caption{Attention patterns.}\label{fig:qa_attn}\end{figure}
Our model achieves exact match of 78.3 on SQuAD \citep{lewis2020bart}.
""")

# ── T05: Abstractive summarisation (ROUGE-L) ──────────────────────────────────
T("t05_summ_rouge", r"""
\section{Introduction}
Abstractive summarisation \citep{see2017get} generates novel sentences.
We build on BART \citep{lewis2020bart} to achieve ROUGE-L of 44.2 on CNN/DM.

\section{Experiments}
\begin{table}[h]
\caption{CNN/DailyMail summarisation results.}
\label{tab:summ}
\begin{tabular}{lccc}
\toprule
Model & ROUGE-1 & ROUGE-2 & ROUGE-L \\
\midrule
PGNet & 39.5 & 17.3 & 36.4 \\
BART & 44.2 & 21.3 & 40.9 \\
Ours & 45.1 & 22.1 & 44.2 \\
\bottomrule
\end{tabular}
\end{table}
Ours achieves ROUGE-L of 44.2, outperforming BART by 3.3 pts.
Figure~\ref{fig:summ_ex} shows an example output.
\begin{figure}[h]\centering\caption{Example summary.}\label{fig:summ_ex}\end{figure}
""")

# ── T06: Language model perplexity ────────────────────────────────────────────
T("t06_lm_ppl", r"""
\section{Introduction}
Language modelling on WikiText-103 is a standard benchmark \citep{bender2021parrots}.
Our model achieves perplexity of 17.2 on WikiText-103 \citep{li2021prefix}.

\section{Experiments}
\begin{table}[h]
\caption{WikiText-103 perplexity.}
\label{tab:ppl}
\begin{tabular}{lc}
\toprule
Model & Perplexity \\
\midrule
GPT-2 & 29.4 \\
Transformer-XL & 21.8 \\
Ours & 17.2 \\
\bottomrule
\end{tabular}
\end{table}
Figure~\ref{fig:ppl_curve} shows perplexity vs epochs.
\begin{figure}[h]\centering\caption{Perplexity curve.}\label{fig:ppl_curve}\end{figure}
Our model achieves perplexity of 17.2, a 4.6-pt improvement over Transformer-XL \citep{lewis2020bart}.
""")

# ── T07: Relation extraction (F1) ────────────────────────────────────────────
T("t07_re_tacred", r"""
\section{Introduction}
Relation extraction maps entity pairs to relations \citep{ye2022generative}.
Our approach achieves F1 of 75.8 on TACRED \citep{rogers2020primer}.

\section{Experiments}
\begin{table}[h]
\caption{TACRED relation extraction results.}
\label{tab:tacred}
\begin{tabular}{lcc}
\toprule
Model & F1 & Prec \\
\midrule
PA-LSTM & 65.1 & 63.2 \\
SpanBERT & 70.8 & 69.5 \\
Ours & 75.8 & 74.3 \\
\bottomrule
\end{tabular}
\end{table}
Figure~\ref{fig:re_overview} illustrates our model.
\begin{figure}[h]\centering\caption{RE model overview.}\label{fig:re_overview}\end{figure}
Ours achieves F1 of 75.8 on TACRED, a 5.0-pt gain over SpanBERT \citep{lewis2020bart}.
""")

# ── T08: Coreference resolution (F1) ─────────────────────────────────────────
T("t08_coref", r"""
\section{Introduction}
Coreference resolution links mentions referring to the same entity \citep{li2021prefix}.
Our model achieves F1 of 82.4 on CoNLL-2012 \citep{ye2022generative}.

\section{Experiments}
\begin{table}[h]
\caption{CoNLL-2012 coreference results.}
\label{tab:coref}
\begin{tabular}{lcc}
\toprule
Model & F1 & Recall \\
\midrule
C2F-Coref & 73.0 & 72.4 \\
SpanBERT-large & 79.6 & 78.9 \\
Ours & 82.4 & 81.7 \\
\bottomrule
\end{tabular}
\end{table}
Ours achieves F1 of 82.4 on CoNLL-2012.
Figure~\ref{fig:coref_eg} shows a coreference example.
\begin{figure}[h]\centering\caption{Coreference example.}\label{fig:coref_eg}\end{figure}
""")

# ── T09: Dialogue state tracking (JGA) ───────────────────────────────────────
T("t09_dst_jga", r"""
\section{Introduction}
Dialogue state tracking (DST) predicts belief states turn by turn.
\citet{rogers2020primer} analyse multilingual capabilities;
we apply this to DST. Our model achieves JGA of 57.3 on MultiWOZ 2.1.

\section{Experiments}
\begin{table}[h]
\caption{MultiWOZ 2.1 DST results.}
\label{tab:dst}
\begin{tabular}{lcc}
\toprule
Model & JGA & Slot-F1 \\
\midrule
TripPy & 53.5 & 87.1 \\
SimpleTOD & 55.7 & 88.9 \\
Ours & 57.3 & 90.2 \\
\bottomrule
\end{tabular}
\end{table}
Our model achieves JGA of 57.3, outperforming SimpleTOD \citep{bender2021parrots} by 1.6 pts.
Figure~\ref{fig:dst_arch} shows the model architecture.
\begin{figure}[h]\centering\caption{DST architecture.}\label{fig:dst_arch}\end{figure}
""")

# ── T10: Semantic parsing (ATIS exact match) ─────────────────────────────────
T("t10_semparse", r"""
\section{Introduction}
Semantic parsing converts utterances to logical forms \citep{lewis2020bart}.
Our model achieves accuracy of 95.8 on ATIS \citep{li2021prefix}.

\section{Experiments}
\begin{table}[h]
\caption{ATIS semantic parsing results.}
\label{tab:atis}
\begin{tabular}{lcc}
\toprule
Model & Accuracy & Exact Match \\
\midrule
Seq2seq & 84.6 & 83.1 \\
LSTM+Attn & 92.3 & 90.7 \\
Ours & 95.8 & 94.2 \\
\bottomrule
\end{tabular}
\end{table}
Figure~\ref{fig:parse_eg} shows parsing examples.
\begin{figure}[h]\centering\caption{Parsing examples.}\label{fig:parse_eg}\end{figure}
Our model achieves accuracy of 95.8 on ATIS, outperforming LSTM+Attn by 3.5 pts \citep{see2017get}.
""")

# ── T11: Machine reading comprehension (multi-hop F1) ────────────────────────
T("t11_mrc_hotpot", r"""
\section{Introduction}
Multi-hop reasoning requires evidence chains across documents.
\citet{ye2022generative} discuss generative approaches; we use extractive reading.
Our model achieves F1 of 79.4 on HotpotQA \citep{rogers2020primer}.

\section{Experiments}
\begin{table}[h]
\caption{HotpotQA distractor results.}
\label{tab:hotpot}
\begin{tabular}{lcc}
\toprule
Model & Ans-F1 & Sup-F1 \\
\midrule
DecompRC & 70.0 & 58.2 \\
GoldEn & 74.3 & 62.0 \\
Ours & 79.4 & 68.1 \\
\bottomrule
\end{tabular}
\end{table}
Figure~\ref{fig:hotpot_arch} illustrates our reasoning chain module.
\begin{figure}[h]\centering\caption{Reasoning chain module.}\label{fig:hotpot_arch}\end{figure}
Ours achieves answer F1 of 79.4 on HotpotQA \citep{lewis2020bart}.
""")

# ── T12: Cross-file table (xfile) ─────────────────────────────────────────────
T("t12_xfile_mnli",
  body=r"""
\section{Introduction}
Natural language inference (NLI) tests sentence understanding.
Following \citet{li2021prefix}, we fine-tune on MNLI.
Our model achieves accuracy of 90.2 on MNLI matched.

\section{Experiments}
\input{tab_mnli}

Our model achieves accuracy of 90.2 on MNLI, 0.6 pts above DeBERTa \citep{lewis2020bart}.
Figure~\ref{fig:nli_arch} shows the model.
\begin{figure}[h]\centering\caption{NLI model.}\label{fig:nli_arch}\end{figure}
""",
  extra={
      "tab_mnli.tex": r"""\begin{table}[h]
\caption{MNLI results.}
\label{tab:mnli}
\begin{tabular}{lcc}
\toprule
Model & Matched & Mismatched \\
\midrule
BERT & 84.6 & 83.4 \\
DeBERTa & 89.6 & 88.9 \\
Ours & 90.2 & 89.5 \\
\bottomrule
\end{tabular}
\end{table}
"""
  })

# ── T13: Multiple tables / multi-metric ──────────────────────────────────────
T("t13_multi_table", r"""
\section{Introduction}
We evaluate on three benchmarks \citep{bender2021parrots}.
Our system achieves F1 of 82.1 on CoNLL-2003 \citep{ye2022generative}.

\section{Experiments}
\begin{table}[h]
\caption{Dataset statistics.}
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
\caption{NER results (F1).}
\label{tab:ner_multi}
\begin{tabular}{lcc}
\toprule
Model & CoNLL-2003 & OntoNotes \\
\midrule
BiLSTM-CRF & 71.1 & 63.4 \\
BERT-NER & 79.3 & 70.2 \\
Ours & 82.1 & 73.8 \\
\bottomrule
\end{tabular}
\end{table}

Our model achieves F1 of 82.1 on CoNLL-2003 \citep{rogers2020primer}.
Figure~\ref{fig:ner_multi} compares models.
\begin{figure}[h]\centering\caption{Multi-dataset NER comparison.}\label{fig:ner_multi}\end{figure}
""")

# ── T14: Prefix-tuning few-shot ───────────────────────────────────────────────
T("t14_fewshot", r"""
\section{Introduction}
Few-shot learning reduces labelling cost \citep{li2021prefix}.
We apply prefix-tuning \citep{lewis2020bart} in few-shot settings.
Our model achieves accuracy of 71.3 on SST-2 with only 16 examples.

\section{Experiments}
\begin{table}[h]
\caption{Few-shot SST-2 accuracy (\%).}
\label{tab:fewshot}
\begin{tabular}{lcccc}
\toprule
Model & 4-shot & 8-shot & 16-shot & Full \\
\midrule
GPT-3 & 54.3 & 58.7 & 63.2 & -- \\
PrefixTune & 61.2 & 66.5 & 69.8 & 90.1 \\
Ours & 63.1 & 68.4 & 71.3 & 91.5 \\
\bottomrule
\end{tabular}
\end{table}

Figure~\ref{fig:fewshot_curve} shows accuracy vs shot count.
\begin{figure}[h]\centering\caption{Few-shot learning curves.}\label{fig:fewshot_curve}\end{figure}
With 16 examples our model achieves accuracy of 71.3, 1.5 pts above PrefixTune \citep{see2017get}.
""")


# ─────────────────────────────────────────────────────────────────────────────
# Perturbation functions
# ─────────────────────────────────────────────────────────────────────────────

CLAIM_PAT = re.compile(
    r"(?:achieves?|obtains?|reaches?|improves?|outperforms?|gains?)"
    r"[^.\n]{0,100}?(\d+\.\d+)",
    re.IGNORECASE,
)

def _perturb(v: str) -> str:
    f = float(v)
    dp = len(v.split(".")[1]) if "." in v else 0
    # Realistic delta: 0.3-1.5 at the last decimal place
    deltas = [0.3, 0.5, 0.8, 1.0, 1.2, 1.5]
    delta = RNG.choice(deltas)
    sign = RNG.choice([-1, 1])
    nf = round(f + sign * delta, dp)
    if nf <= 0 or nf > f * 2:
        nf = round(f + delta, dp)
    return f"{nf:.{dp}f}"

def apply_P1(body: str) -> tuple[str, dict]:
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.count("&") >= 2 or line.lstrip().startswith("%"):
            continue
        m = CLAIM_PAT.search(line)
        if m:
            orig, new = m.group(1), _perturb(m.group(1))
            lines[i] = line[:m.start(1)] + new + line[m.end(1):]
            return "\n".join(lines), {
                "type": "P1", "line": i+1,
                "original": orig, "modified": new,
                "context": line.strip()[:80],
            }
    return body, {}

def apply_P3(body: str) -> tuple[str, dict]:
    fake = f"hallucinated_ref_{RNG.randint(2020,2024)}_{RNG.randint(100,999)}"
    m = re.search(r"\\cite[tp]?\{([^}]+)\}", body)
    if m:
        insert = body[:m.end()] + f"\\citep{{{fake}}}" + body[m.end():]
        return insert, {"type": "P3", "fake_key": fake,
                        "line": body[:m.start()].count("\n")+1}
    return body, {}

def apply_P4(body: str) -> tuple[str, dict]:
    m = re.search(r"\\cite[tp]?\{([^}]+)\}", body)
    if m:
        orig = m.group(1).split(",")[0].strip()
        broken = orig + "_TYPO"
        new_body = body.replace(f"{{{orig}}}", f"{{{broken}}}", 1)
        return new_body, {"type": "P4", "original_key": orig, "broken_key": broken,
                          "line": body[:m.start()].count("\n")+1}
    return body, {}

def apply_P5(body: str) -> tuple[str, dict]:
    fake = f"fig:nonexistent_{RNG.randint(100,999)}"
    lines = body.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if (s and not s.startswith("\\") and not s.startswith("%")
                and len(s) > 20 and line.count("&") < 2
                and "\\ref{" not in line):
            lines[i] = line.rstrip() + f" (see Figure~\\ref{{{fake}}})"
            return "\n".join(lines), {"type": "P5", "fake_label": fake, "line": i+1}
    return body, {}

def apply_P6(body: str) -> tuple[str, dict]:
    m = re.search(r"\\label\{(fig:[^}]+)\}", body)
    if m:
        key = m.group(1)
        new_body = body.replace(m.group(0), "", 1)
        return new_body, {"type": "P6", "removed_label": key,
                          "line": body[:m.start()].count("\n")+1}
    return body, {}

# Reference perturbations
def apply_R1(bib: str, ref: dict) -> tuple[str, dict]:
    fake = f"10.{RNG.randint(10000,99999)}/fakejour.{RNG.randint(1000,9999)}.{RNG.randint(100,999)}"
    new_bib = bib.replace(ref["doi"], fake, 1)
    return new_bib, {"type": "R1", "key": ref["key"],
                     "original_doi": ref["doi"], "fake_doi": fake}

def apply_R2(bib: str, ref: dict) -> tuple[str, dict]:
    # Fabricate a clearly wrong title by replacing content words with generic NLP terms.
    # Must achieve < 0.60 similarity so the gate raises ERROR (not just WARNING).
    fake_titles = [
        "Neural Approaches to Natural Language Processing with Deep Networks",
        "Improving Text Classification Using Pretrained Transformer Models",
        "A Survey of Attention Mechanisms in Sequence-to-Sequence Learning",
        "End-to-End Training of Neural Language Models on Large Corpora",
        "Efficient Fine-Tuning of Large Language Models for Downstream Tasks",
        "Multi-Task Learning for Natural Language Understanding and Generation",
        "Contextual Embeddings for Cross-Lingual Transfer in Low-Resource Settings",
        "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
    ]
    # Pick a fake title that is maximally different from the real one
    from difflib import SequenceMatcher
    real_lower = ref["title"].lower()
    chosen = min(fake_titles, key=lambda t: SequenceMatcher(None, real_lower, t.lower()).ratio())
    new_bib = bib.replace(ref["title"], chosen, 1)
    return new_bib, {"type": "R2", "key": ref["key"],
                     "original_title": ref["title"], "fake_title": chosen}

def apply_R3(bib: str, ref: dict) -> tuple[str, dict]:
    # Add a fake extra author
    orig = " and ".join(ref["authors"])
    fake_author = RNG.choice(["John Q. Fabricated", "Alice B. Invented",
                               "Bob C. Generated", "Carol D. Hallucinated"])
    new_authors = orig + f" and {fake_author}"
    new_bib = bib.replace(orig, new_authors, 1)
    return new_bib, {"type": "R3", "key": ref["key"],
                     "original_n": len(ref["authors"]),
                     "fake_author": fake_author}


# ─────────────────────────────────────────────────────────────────────────────
# Case factory
# ─────────────────────────────────────────────────────────────────────────────

def build():
    cases: list[dict] = []
    _id = 0

    for tmpl in TEMPLATES:
        clean_tex, clean_bib, clean_extra = _wrap(
            tmpl["body"], tmpl["extra"], tmpl.get("bib", "")
        )

        def add(gate, perturb, ptex, pbib, meta, pextra=None):
            nonlocal _id
            cid = f"{tmpl['name']}_{perturb}_{_id}"; _id += 1
            cases.append({
                "id": cid, "template": tmpl["name"],
                "gate": gate, "perturbation": perturb, "label": 1,
                "injected_at": meta,
                "tex": ptex, "bib": pbib,
                "clean_tex": clean_tex, "clean_bib": clean_bib,
                "extra_files": pextra or clean_extra,
                "clean_extra_files": clean_extra,
            })
            cid2 = f"{tmpl['name']}_CLEAN_{gate}_{_id}"; _id += 1
            cases.append({
                "id": cid2, "template": tmpl["name"],
                "gate": gate, "perturbation": "CLEAN", "label": 0,
                "injected_at": {},
                "tex": clean_tex, "bib": clean_bib,
                "clean_tex": clean_tex, "clean_bib": clean_bib,
                "extra_files": clean_extra, "clean_extra_files": clean_extra,
            })

        # data_integrity: P1
        body_p1, meta_p1 = apply_P1(tmpl["body"])
        if meta_p1:
            tex_p1, bib_p1, _ = _wrap(body_p1, tmpl["extra"], tmpl.get("bib",""))
            add("data_integrity", "P1", tex_p1, bib_p1, meta_p1)

        # data_integrity: P1_xfile (only for cross-file template)
        if tmpl["name"] == "t12_xfile_mnli" and meta_p1:
            meta_xf = dict(meta_p1, type="P1_xfile")
            tex_xf, bib_xf, _ = _wrap(body_p1, tmpl["extra"], tmpl.get("bib",""))
            nonlocal_id = _id
            cid = f"{tmpl['name']}_P1_xfile_{_id}"; _id += 1
            cases.append({
                "id": cid, "template": tmpl["name"],
                "gate": "data_integrity", "perturbation": "P1_xfile", "label": 1,
                "injected_at": meta_xf,
                "tex": tex_xf, "bib": bib_xf,
                "clean_tex": clean_tex, "clean_bib": clean_bib,
                "extra_files": tmpl["extra"], "clean_extra_files": clean_extra,
            })
            cid2 = f"{tmpl['name']}_CLEAN_data_xfile_{_id}"; _id += 1
            cases.append({
                "id": cid2, "template": tmpl["name"],
                "gate": "data_integrity", "perturbation": "CLEAN", "label": 0,
                "injected_at": {},
                "tex": clean_tex, "bib": clean_bib,
                "clean_tex": clean_tex, "clean_bib": clean_bib,
                "extra_files": clean_extra, "clean_extra_files": clean_extra,
            })

        # citation: P3, P4
        body_p3, meta_p3 = apply_P3(tmpl["body"])
        if meta_p3:
            tex_p3, bib_p3, _ = _wrap(body_p3, tmpl["extra"], tmpl.get("bib",""))
            add("citation_bib_consistency", "P3", tex_p3, bib_p3, meta_p3)

        body_p4, meta_p4 = apply_P4(tmpl["body"])
        if meta_p4:
            tex_p4, bib_p4, _ = _wrap(body_p4, tmpl["extra"], tmpl.get("bib",""))
            add("citation_bib_consistency", "P4", tex_p4, bib_p4, meta_p4)

        # figure: P5, P6
        body_p5, meta_p5 = apply_P5(tmpl["body"])
        if meta_p5:
            tex_p5, bib_p5, _ = _wrap(body_p5, tmpl["extra"], tmpl.get("bib",""))
            add("figure_table_crossref", "P5", tex_p5, bib_p5, meta_p5)

        body_p6, meta_p6 = apply_P6(tmpl["body"])
        if meta_p6:
            tex_p6, bib_p6, _ = _wrap(body_p6, tmpl["extra"], tmpl.get("bib",""))
            add("figure_table_crossref", "P6", tex_p6, bib_p6, meta_p6)

        # reference: R1, R2, R3 — use different real refs per template to vary
        ref = RNG.choice(REAL_REFS)
        for apply_fn, rtype in [(apply_R1, "R1"), (apply_R2, "R2"), (apply_R3, "R3")]:
            new_bib, meta_r = apply_fn(clean_bib, ref)
            if meta_r:
                add("reference_authenticity", rtype, clean_tex, new_bib, meta_r)

    # Shuffle to mix gates
    bug_cases   = [c for c in cases if c["label"] == 1]
    clean_cases = [c for c in cases if c["label"] == 0]
    RNG.shuffle(bug_cases)
    RNG.shuffle(clean_cases)
    # Interleave bug/clean pairs
    final = []
    for b, cl in zip(bug_cases, clean_cases):
        final.extend([b, cl])

    OUT.write_text(json.dumps(final, indent=2, ensure_ascii=False), encoding="utf-8")

    from collections import Counter
    by_gate    = Counter(c["gate"] for c in final)
    by_perturb = Counter(c["perturbation"] for c in final)
    by_label   = Counter(c["label"] for c in final)
    print(f"Wrote {len(final)} cases to {OUT}")
    print(f"  gate:    {dict(sorted(by_gate.items()))}")
    print(f"  perturb: {dict(sorted(by_perturb.items()))}")
    print(f"  label:   bug={by_label[1]}  clean={by_label[0]}")

if __name__ == "__main__":
    build()
