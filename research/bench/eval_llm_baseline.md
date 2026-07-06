# ScholarLint LLM Baseline Evaluation

Benchmark: **benchmark_v2** (52 cases, bug=26, clean=26)

Evaluation: full LaTeX paper → LLM binary classification (bug/no-bug)

## gpt-5.5

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 4 | 0 | 5 | 9 | 1.00 | 0.44 | 0.61 | 18 |
| citation_bib_consistency | 10 | 10 | 0 | 0 | 0.50 | 1.00 | 0.67 | 20 |
| figure_table_crossref | 7 | 0 | 0 | 7 | 1.00 | 1.00 | 1.00 | 14 |
| **Overall** | - | - | - | - | **0.83** | **0.81** | **0.76** | - |

## claude-opus-4.7

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 5 | 2 | 4 | 7 | 0.71 | 0.56 | 0.62 | 18 |
| citation_bib_consistency | 10 | 5 | 0 | 5 | 0.67 | 1.00 | 0.80 | 20 |
| figure_table_crossref | 7 | 0 | 0 | 7 | 1.00 | 1.00 | 1.00 | 14 |
| **Overall** | - | - | - | - | **0.79** | **0.85** | **0.81** | - |

## Ours (ScholarLint)

| Gate | TP | FP | FN | TN | P | R | F1 | N |
|------|----|----|----|----|----|---|-----|---|
| data_integrity | 5 | 0 | 4 | 9 | 1.00 | 0.56 | 0.71 | 18 |
| citation_bib_consistency | 10 | 0 | 0 | 10 | 1.00 | 1.00 | 1.00 | 20 |
| figure_table_crossref | 7 | 0 | 0 | 7 | 1.00 | 1.00 | 1.00 | 14 |
| **Overall** | - | - | - | - | **1.00** | **0.85** | **0.90** | - |

## Summary: Macro F1 Comparison

| Gate | Ours | gpt-5.5 | claude-opus-4.7 |
|------|------|---------|-----------------|
| data_integrity | 0.71 | 0.61 | 0.62 |
| citation_bib_consistency | 1.00 | 0.67 | 0.80 |
| figure_table_crossref | 1.00 | 1.00 | 1.00 |
