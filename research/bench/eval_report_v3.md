# ScholarLint Benchmark v3

Cases: **134**  (bug=67, clean=67)

Perturbation types: P1, P1_xfile, P3, P4, P5, P6, R1, R2, R3
Eval method: **differential** — pred=1 iff issues(perturbed) > issues(clean)

## B0 (legacy regex)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 1 | 0 | 9 | 10 | 1.00 | 0.10 | 0.18 | 20 |
| citation_bib_consistency | 0 | 0 | 18 | 18 | 0.00 | 0.00 | 0.00 | 36 |
| figure_table_crossref | 0 | 0 | 12 | 12 | 0.00 | 0.00 | 0.00 | 24 |
| reference_authenticity | 0 | 0 | 27 | 27 | 0.00 | 0.00 | 0.00 | 54 |
| **Overall (macro)** | - | - | - | - | **0.25** | **0.03** | **0.05** | - |

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 6 | 0 | 4 | 10 | 1.00 | 0.60 | 0.75 | 20 |
| citation_bib_consistency | 18 | 0 | 0 | 18 | 1.00 | 1.00 | 1.00 | 36 |
| figure_table_crossref | 12 | 0 | 0 | 12 | 1.00 | 1.00 | 1.00 | 24 |
| reference_authenticity | 8 | 0 | 19 | 27 | 1.00 | 0.30 | 0.46 | 54 |
| **Overall (macro)** | - | - | - | - | **1.00** | **0.72** | **0.80** | - |

## Summary: Macro F1

| Gate | B0 | Ours |
|------|----|------|
| data_integrity | 0.18 | 0.75 |
| citation_bib_consistency | 0.00 | 1.00 |
| figure_table_crossref | 0.00 | 1.00 |
| reference_authenticity | 0.00 | 0.46 |
