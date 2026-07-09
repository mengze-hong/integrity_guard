# CHANGELOG

## 2026-07-09 — NCG table parsing 三项修复

### 修复
- `_is_header_row`: 改用 standalone number 判断（旧逻辑 `_NUMBER_PATTERN` 把 `Ans-F1`, `GPT-2`, `BERT-base` 里的数字误判为 numeric cell，导致表头行被当成数据行）
- `_extract_tables` data row 首列: 同样改用 standalone number 判断，避免 `GPT-2 & 29.4` 里 `GPT-2` 被当作数值并提取 `-2.0`
- `_scope_sim`: 新增 `_STATS_COL_HDRS` 正则，过滤 Train/Test/Dev/Size 等数据集统计列，防止与 NER/performance 表混淆
- `_scope_sim` threshold: 0.75 → 0.6，允许 metric 单独命中（metric+col 匹配时足够可信）
- `_norm`: 去除括号字符 `()`，使 `(F1)` 能被 normalize 为 `f1` 完成 caption 匹配

### 结果
- data_integrity F1: **0.75 → 0.93**（与 claude-opus-4.7 standalone 持平）
- FP 仍为 0（Precision = 1.00）
- 剩余 2 个 FN 均为 `\input{...}` 跨文件表格（benchmark 评测限制，非系统 bug）

---

## 2026-07-08 — Hybrid NCG + benchmark_v3

- feat: Hybrid NCG — LLM 提取 claim + 规则验证（data F1 0.60→0.75）
- feat: benchmark_v3 226 cases，4 gates，14 templates
- feat: LLM baseline 评测 gpt-5.5 + claude-opus-4.7
- feat: i18n 中英文切换（右上角）
- fix: issue 点击跳转到对应文件+行
- fix: LaTeX 注释行不参与检测（`stripped_text`）
