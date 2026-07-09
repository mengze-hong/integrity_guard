# ScholarLint Benchmark v3

Cases: **226**  (bug=113, clean=113)

Perturbation types: P1, P1_xfile, P3, P4, P5, P6, R1, R2, R3
Eval method: **differential** — pred=1 iff issues(perturbed) > issues(clean)

## B0 (legacy regex)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 2 | 0 | 13 | 15 | 1.00 | 0.13 | 0.23 | 30 |
| citation_bib_consistency | 0 | 0 | 28 | 28 | 0.00 | 0.00 | 0.00 | 56 |
| figure_table_crossref | 0 | 0 | 28 | 28 | 0.00 | 0.00 | 0.00 | 56 |
| reference_authenticity | 0 | 0 | 42 | 42 | 0.00 | 0.00 | 0.00 | 84 |
| **Overall (macro)** | - | - | - | - | **0.25** | **0.03** | **0.06** | - |

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 13 | 0 | 2 | 15 | 1.00 | 0.87 | 0.93 | 30 |
| citation_bib_consistency | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| figure_table_crossref | 28 | 0 | 0 | 28 | 1.00 | 1.00 | 1.00 | 56 |
| reference_authenticity | 42 | 0 | 0 | 42 | 1.00 | 1.00 | 1.00 | 84 |
| **Overall (macro)** | - | - | - | - | **1.00** | **0.97** | **0.98** | - |

## Summary: Macro F1

| Gate | B0 | Ours |
|------|----|------|
| data_integrity | 0.23 | 0.93 |
| citation_bib_consistency | 0.00 | 1.00 |
| figure_table_crossref | 0.00 | 1.00 |
| reference_authenticity | 0.00 | **1.00** |
