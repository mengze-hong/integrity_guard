# ScholarLint Benchmark Evaluation

Total cases: **56** (bug=26, clean=30)

## B0 (legacy regex)

| Gate | TP | FP | FN | TN | P | R | F1 |
|------|----|----|----|----|---|---|-----|
| data_integrity | 10 | 4 | 1 | 6 | 0.71 | 0.91 | 0.80 |
| citation_bib_consistency | 0 | 0 | 10 | 10 | 0.00 | 0.00 | 0.00 |
| figure_table_crossref | 0 | 0 | 5 | 10 | 0.00 | 0.00 | 0.00 |
| **Overall (macro)** | - | - | - | - | **0.24** | **0.30** | **0.27** |

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 |
|------|----|----|----|----|---|---|-----|
| data_integrity | 0 | 0 | 11 | 10 | 0.00 | 0.00 | 0.00 |
| citation_bib_consistency | 1 | 0 | 9 | 10 | 1.00 | 0.10 | 0.18 |
| figure_table_crossref | 5 | 0 | 0 | 10 | 1.00 | 1.00 | 1.00 |
| **Overall (macro)** | - | - | - | - | **0.67** | **0.37** | **0.39** |

## Summary Comparison (Macro F1)

| Gate | B0 | Ours |
|------|----|------|
| data_integrity | 0.80 | 0.00 |
| citation_bib_consistency | 0.00 | 0.18 |
| figure_table_crossref | 0.00 | 1.00 |
