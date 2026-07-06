# False-Positive Audit Report

Papers audited: **39** (real submissions under `uploads/`)
Gates: structure, citations, figures, data, writing (reference authenticity skipped — needs live APIs).

> On real published/submitted papers, most ERRORs are **candidate false positives**. High-frequency messages = systematic FP to fix first.

## ERROR frequency by gate (papers flagged / total)

### structure_integrity — 31/39 papers with ≥1 error
- `62×` \ref{fig
- `31×` 引用的文件不存在
- `31×` \ref{tab

### citation_bib_consistency — 31/39 papers with ≥1 error
- `31×` 未定义引用

### figure_table_crossref — 39/39 papers with ≥1 error
- `62×` \ref{fig
- `31×` \ref{tab
- `5×` Figure 1 (\label{fig
- `3×` Figure 16 (\label{fig
- `3×` Table 6 (\label{tab
- `3×` Table 7 (\label{tab
- `3×` Table 10 (\label{tab
- `3×` Table 11 (\label{tab
- `3×` Table 15 (\label{tab
- `1×` Table 2 (\label{tab
- `1×` Table 5 (\label{tab

### data_integrity — 0/39 papers with ≥1 error
- (no errors)

### writing_quality — 0/39 papers with ≥1 error
- (no errors)

## WARNING frequency by gate (top messages)

### structure_integrity
- `32×` 图片文件不存在
- `6×` 图片文件过大

### citation_bib_consistency
- `4×` 孤立条目

### writing_quality
- `5×` 投稿模式为 [final]，double-blind 应使用 [review]
- `5×` 建议添加 Ethics Statement 章节
- `4×` 发现 47 个超长句子
- `3×` 发现 61 个超长句子
- `3×` 两个段落高度相似
- `1×` 发现 46 个超长句子

## Per-paper detail

### 0586ca74
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 07c3d865f33e
- **structure_integrity**: score=96 pass=True errors=0 warnings=2
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=1
- **figure_table_crossref**: score=70 pass=False errors=6 warnings=0
    - [E] Figure 16 (\label{fig:prompt_templates}) 在正文中从未被引用
    - [E] Table 6 (\label{tab:ablation_summary}) 在正文中从未被引用
    - [E] Table 7 (\label{tab:benchmark_comparison}) 在正文中从未被引用
    - [E] Table 10 (\label{tab:task1_3class_ablation}) 在正文中从未被引用
    - [E] Table 11 (\label{tab:task1_prompt_ablation}) 在正文中从未被引用
    - [E] Table 15 (\label{tab:ablation_sysprompt}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=90 pass=True errors=0 warnings=2

### 0b1ba81e
- **structure_integrity**: score=100 pass=True errors=0 warnings=0
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=0
- **figure_table_crossref**: score=95 pass=False errors=1 warnings=0
    - [E] Figure 1 (\label{fig:overview}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=85 pass=True errors=0 warnings=3

### 0b278a29
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 12d9c29c
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 15b88d21
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 316dd0a3
- **structure_integrity**: score=100 pass=True errors=0 warnings=0
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=1
- **figure_table_crossref**: score=95 pass=False errors=1 warnings=0
    - [E] Figure 1 (\label{fig:overview}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=85 pass=True errors=0 warnings=3

### 3254de2b4f62
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 41283a4d
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 4d44d6f4
- **structure_integrity**: score=100 pass=True errors=0 warnings=0
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=0
- **figure_table_crossref**: score=95 pass=False errors=1 warnings=0
    - [E] Figure 1 (\label{fig:overview}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=85 pass=True errors=0 warnings=3

### 53edfcfb
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 55105ee3
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 5b57c0ac
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 69e512db
- **structure_integrity**: score=96 pass=True errors=0 warnings=2
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=1
- **figure_table_crossref**: score=70 pass=False errors=6 warnings=0
    - [E] Figure 16 (\label{fig:prompt_templates}) 在正文中从未被引用
    - [E] Table 6 (\label{tab:ablation_summary}) 在正文中从未被引用
    - [E] Table 7 (\label{tab:benchmark_comparison}) 在正文中从未被引用
    - [E] Table 10 (\label{tab:task1_3class_ablation}) 在正文中从未被引用
    - [E] Table 11 (\label{tab:task1_prompt_ablation}) 在正文中从未被引用
    - [E] Table 15 (\label{tab:ablation_sysprompt}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=90 pass=True errors=0 warnings=2

### 6a7c8e94
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 6d7afbda
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 6f18785b
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 728856ab5c23
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 74043894
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 7ac7ebe6
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 7f3c1418
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 87f3cdb0
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 8ee28b5e
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 9038fb27
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 9068651d
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### 93cd1819
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### a7a12d78703e
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### af7a8029
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### c5843edd
- **structure_integrity**: score=95 pass=True errors=0 warnings=1
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=0
- **figure_table_crossref**: score=85 pass=False errors=3 warnings=0
    - [E] Figure 1 (\label{fig:overview}) 在正文中从未被引用
    - [E] Table 2 (\label{tab:diagnostic}) 在正文中从未被引用
    - [E] Table 5 (\label{tab:route_selection}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=85 pass=True errors=0 warnings=3

### c7dd4c03
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### c980fefa
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### d8ed5906
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### de81f9bd
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### e237d467
- **structure_integrity**: score=100 pass=True errors=0 warnings=0
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=0
- **figure_table_crossref**: score=95 pass=False errors=1 warnings=0
    - [E] Figure 1 (\label{fig:overview}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=85 pass=True errors=0 warnings=3

### ee6645e1
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### f339d9f7
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### f7b9eacd42cf
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### f95b3087
- **structure_integrity**: score=50 pass=False errors=4 warnings=1
    - [E] 引用的文件不存在: \input{tables/results}
    - [E] \ref{fig:architecture} 引用了不存在的 label
    - [E] \ref{tab:results} 引用了不存在的 label
    - [E] \ref{fig:missing} 引用了不存在的 label
- **citation_bib_consistency**: score=80 pass=False errors=1 warnings=0
    - [E] 未定义引用: \cite{nonexistent_key} → 编译后 PDF 中将显示 '?'
- **figure_table_crossref**: score=100 pass=False errors=3 warnings=0
    - [E] \ref{fig:architecture} 引用了不存在的图表标签
    - [E] \ref{fig:missing} 引用了不存在的图表标签
    - [E] \ref{tab:results} 引用了不存在的图表标签
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=100 pass=True errors=0 warnings=0

### test_real
- **structure_integrity**: score=96 pass=True errors=0 warnings=2
- **citation_bib_consistency**: score=100 pass=True errors=0 warnings=1
- **figure_table_crossref**: score=70 pass=False errors=6 warnings=0
    - [E] Figure 16 (\label{fig:prompt_templates}) 在正文中从未被引用
    - [E] Table 6 (\label{tab:ablation_summary}) 在正文中从未被引用
    - [E] Table 7 (\label{tab:benchmark_comparison}) 在正文中从未被引用
    - [E] Table 10 (\label{tab:task1_3class_ablation}) 在正文中从未被引用
    - [E] Table 11 (\label{tab:task1_prompt_ablation}) 在正文中从未被引用
    - [E] Table 15 (\label{tab:ablation_sysprompt}) 在正文中从未被引用
- **data_integrity**: score=100 pass=True errors=0 warnings=0
- **writing_quality**: score=90 pass=True errors=0 warnings=2