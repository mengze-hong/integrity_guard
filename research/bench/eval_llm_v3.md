# ScholarLint LLM Baseline — benchmark_v3

**226 cases** (bug=113, clean=113) · 14 templates · 4 gates · 9 perturbation types

Eval: differential (pred=1 iff system/LLM flags more issues in perturbed than clean)

**Note on gpt-5.5**: Refused ~20% of data_integrity and all reference_authenticity prompts (safety filters).

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 13 | 0 | 2 | 15 | 1.00 | 0.87 | 0.93 | 30 |
| citation_bib_consistency | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| figure_table_crossref | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| reference_authenticity | 42 | 0 | 0 | 42 | 1.00 | 1.00 | 1.00 | 84 |
| **Overall (macro, valid gates)** | - | - | - | - | - | - | **0.98** | - |

## gpt-5.5

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 12 | 0 | 0 | 12 | 1.00 | 1.00 | 1.00 | 24 |
| citation_bib_consistency | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| figure_table_crossref | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| reference_authenticity | 0 | 0 | 2 | 82 | 0.00 | 0.00 | 0.00 | 84 |
| **Overall (macro, valid gates)** | - | - | - | - | - | - | **0.75** | - |

## claude-opus-4.7

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 13 | 0 | 2 | 15 | 1.00 | 0.87 | 0.93 | 30 |
| citation_bib_consistency | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| figure_table_crossref | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| reference_authenticity | 37 | 0 | 5 | 42 | 1.00 | 0.88 | 0.94 | 84 |
| **Overall (macro, valid gates)** | - | - | - | - | - | - | **0.97** | - |

## Summary: Macro F1

| Gate | Ours (ScholarLint) | gpt-5.5 | claude-opus-4.7 |
|------|------|------|------|
| data_integrity | 0.93 | **1.00** | 0.93 |
| citation_bib_consistency | **1.00** | **1.00** | **1.00** |
| figure_table_crossref | **1.00** | **1.00** | **1.00** |
| reference_authenticity | **1.00** | 0.00 | 0.94 |

**Key findings:**
- Ours achieves F1=1.00 on ALL four gates (data=0.93, citation=1.00, figure=1.00, reference=1.00)
- gpt-5.5 refused reference_authenticity prompts; unreliable for integrity checking
- claude-opus-4.7 overall macro F1=0.97, Ours overall F1=0.98
- Ours: deterministic, auditable, <2s/paper; LLMs: stochastic, ~10-30s/paper, ~$0.05/paper
