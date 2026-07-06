# ScholarLint Benchmark v2 (Full-Paper Mode)

Cases: **52**  (bug=26, clean=26)

Evaluation method: **differential** — pred=1 iff gate(perturbed) > gate(clean)

## B0 (legacy regex)

| Gate | TP | FP | FN | TN | P | R | F1 |
|------|----|----|----|----|---|---|-----|
| data_integrity | 1 | 0 | 8 | 9 | 1.00 | 0.11 | 0.20 |
| citation_bib_consistency | 0 | 0 | 10 | 10 | 0.00 | 0.00 | 0.00 |
| figure_table_crossref | 0 | 0 | 7 | 7 | 0.00 | 0.00 | 0.00 |
| **Overall** | - | - | - | - | **0.33** | **0.04** | **0.07** |

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 |
|------|----|----|----|----|---|---|-----|
| data_integrity | 5 | 0 | 4 | 9 | 1.00 | 0.56 | 0.71 |
| citation_bib_consistency | 10 | 0 | 0 | 10 | 1.00 | 1.00 | 1.00 |
| figure_table_crossref | 7 | 0 | 0 | 7 | 1.00 | 1.00 | 1.00 |
| **Overall** | - | - | - | - | **1.00** | **0.85** | **0.90** |

## Summary (Macro F1)

| Gate | B0 | Ours |
|------|----|------|
| data_integrity | 0.20 | 0.71 |
| citation_bib_consistency | 0.00 | 1.00 |
| figure_table_crossref | 0.00 | 1.00 |
