# 方法设计：NCG — Numerical Claim Grounding（正文数值断言的表格接地验证）

> 目标：把 `gate_data.py::_check_text_table_consistency` 从 regex 升级为一个可发表的方法，
> 支撑 EMNLP Demo 的"方法 + 实验"部分。
> 定位：lightweight、zero-training、human-in-the-loop，成本随**歧义度**增长而非随论文长度增长。
> 最后更新：2026-07-03

---

## 0. 问题定义

学术论文正文中充斥数值断言（numerical claims）：
- 绝对型："our method achieves **92.3** F1 on SQuAD"
- 比较型："outperforms BERT by **2.1** points"
- 聚合型："average improvement of **3.5%** across five datasets"

这些数字**应当被表格数据支撑**。不一致的来源：
1. **数据篡改**（misconduct）：正文改了数字但表格没改，或反之（耿同学式）
2. **陈旧文本**（honest error）：更新了实验表格，忘了改正文
3. **张冠李戴**：引用了错误的 cell（把 baseline 的数当成自己的）
4. **夸大**：比较型断言的 delta 与实际表格值不符

**任务**：给定论文 `(text, tables)`，判定每条数值断言 `c` 相对于表格集合 `T` 的状态：
`verdict(c, T) ∈ {Supported, Contradicted, Ungroundable}`。
只有 **Contradicted 且高置信** 的断言作为 issue 上报，交由作者/导师核实（human-in-the-loop）。

### 与现有工作的区分（Related Work 用）
- **SciClaimEval (2026, arXiv:2602.07621)**：跨模态 claim 验证 **benchmark**，人工标注，评测重型模型。
  → 我们是**可部署的方法 + 成本感知架构**，面向投稿前作者侧，benchmark 由扰动**自动**构造（难度可控）。
- **statcheck (Nuijten 2016)**：只重算 p 值。→ 我们做任意数值断言的表格接地。
- **TAB-AUDIT (2026, arXiv:2603.19712)**：检测**整张表**是否 AI 伪造（likelihood mismatch），需训 RandomForest。
  → 我们检测**正文与表格的一致性**，零训练，且定位到具体 claim。

---

## 1. 结构化表示

### 1.1 数值断言 Claim
```
c = (v, U, τ, S, loc)
  v   : float                     # 断言的数值
  U   : unit ∈ {raw, %, pt, ×, ±} # 单位/格式
  τ   : type ∈ {absolute, comparative, aggregate}
  S   : scope = {method?, metric?, dataset?}  # 从上下文窗口抽取的语义作用域
  loc : (file, line)
```
比较型额外携带：`rel = (op, operand_a, operand_b)`，`op ∈ {>, <, =, +δ, ×k}`。

**抽取**：正则定位数字 → 取左右 ±N token 窗口 → 用关键词表/词典抽 metric（F1/BLEU/accuracy/…）、
从表 caption 与全局 method/dataset 名单做字典匹配填充 S。**不依赖重型 NER**（保持轻量）。

### 1.2 表格 Cell（需增强现有 `_extract_tables`）
```
t = (v, rowhdr, colhdr, tableid, caption)
  semantic_address = (rowhdr, colhdr)   # e.g. ("BERT", "F1")
```
**当前代码缺行/列头**：`_extract_tables` 只存 `rows: list[list[float]]`。
需扩展：识别首行为列头、首列为行头（启发式：首行/首列含非数值文本），
构建 `cell_index: dict[semantic_address → value]` 与 `value_index: dict[round(value) → list[cell]]`。

---

## 2. 双向接地算法（核心新点）

对每条 claim `c`，从两个方向对齐到 cell：

### 方向 A — 值优先（value-first）
```
candidates_A = value_index[round(c.v, tol)]        # 值≈c.v 的所有 cell
```
用于回答"这个数在表里存在吗、可能来自哪"。

### 方向 B — 作用域优先（scope-first）★关键
```
target_cell = argmax_t  lexical_sim(c.S, t.semantic_address ∪ t.caption)
```
找到 claim "指向"的那个 cell（不管值对不对）。

### 判定逻辑
```
if target_cell 存在 (作用域高置信):
    if |target_cell.v - c.v| ≤ tol:   → Supported
    else:                              → Contradicted     ★钱在这里
                                          evidence = (c, target_cell)
elif candidates_A 非空 but 作用域不匹配任一 candidate:
                                       → 可能张冠李戴 (weak Contradicted / info)
elif candidates_A 为空 and 无 target:  → Ungroundable
else:                                  → 送 Tier 2 裁决
```

**tol（容差）**：按 U 自适应——舍入到正文声称的小数位再比（92.34→"92.3" 不算矛盾），
避免舍入漂移误报。这是误报控制的关键。

### 比较型断言（Tier 1 结构化关系检查）
```
"A outperforms B by δ" →
  接地 A→cell_a, B→cell_b (scope-first)
  computed_δ = cell_a.v - cell_b.v
  if |computed_δ - stated_δ| > tol → Contradicted (relation)
```
纯算术，零成本。

---

## 3. 三级成本感知架构（lightweight 卖点）

| Tier | 手段 | 成本 | 覆盖 |
|------|------|------|------|
| **0** | 值优先+作用域优先规则匹配 | ~0（本地） | 精确匹配 / 明确矛盾 → 多数 claim |
| **1** | 比较型断言的结构化算术 | ~0（本地） | 所有 comparative/aggregate |
| **2** | LLM 裁决，**仅输入"该句 + Top-k 候选 cell"** | 有界 token（与论文长度无关） | 仅剩余歧义：多候选、指标名模糊、hedged 表述 |

**Tier 2 prompt 只喂局部**（一句话 + 几个候选 cell 的结构化描述），不喂全文
→ 每次调用 token 恒定，且大部分 claim 在 Tier 0/1 已解决。
**报告"各 Tier 解决占比"**：证明 LLM 触发率低 → 对 full-LLM baseline 的成本碾压。

置信度：Tier 0/1 规则命中给高置信；Tier 2 用 LLM 返回的判据 + 作用域相似度加权。
仅 `Contradicted ∧ conf ≥ θ` 上报为 ERROR/WARNING，`Ungroundable` 默认不报（可选 info）。

---

## 4. 自动 Benchmark 构造（无需人工标注）

### 语料
N 篇真实 arXiv 论文源码（有表格 + 数值断言；优先 ACL/ML 领域，用 arXiv source dump）。

### 正样本（consistent）
用 Tier 0 抽出**已接地且一致**的 claim，作为 silver 正样本。
⚠️ **假设原论文正确**（大体成立）——需在 limitations 明确声明此 silver-label 假设。

### 负样本（inconsistent）— 注入扰动
对正样本 claim 施加受控扰动，生成带标签的矛盾：

| 扰动 | 操作 | 模拟的真实错误 |
|------|------|--------------|
| **P1 值替换** | 正文值 → 邻近错值 (v±Δ) | 篡改 / typo |
| **P2 关系翻转** | 改比较型 δ 或方向 | 夸大提升 |
| **P3 邻格混淆** | 换成同表兄弟 cell 的值 | 张冠李戴 |
| **P4 舍入漂移** | 92.34→92.4（应**不**报） | 测误报控制（负控制组） |

Δ 可扫描（0.1 / 0.5 / 1.0 / 2.0）→ 画**检测率 vs 扰动幅度**曲线，展示灵敏度。
P4 单独作为 negative control，验证不误报。

### 规模建议
- Demo 起步：30–50 篇，每篇若干 claim → 数百条标注样本，1–2 天可跑通。
- 若冲 short paper：扩到 100–200 篇。

---

## 5. Baselines 与评测

### Baselines（递进，全部可复现）
- **B0 — Regex**：现有 `_check_text_table_consistency`（我们要超越的起点）
- **B1 — 全局精确匹配**：数字在任意表中出现即 Supported（无作用域）
- **B2 — Embedding 检索**：embed(claim 句) vs embed(cell 描述)，cosine top-1 + 阈值
- **B3 — 全文 LLM**：整篇 text+tables 喂 LLM，"列出不一致的数字"（强但贵）
- **Ours — NCG（三级）**

### 指标
1. **检测质量**：矛盾 claim 的 Precision / Recall / F1
2. **误报率 FPR**：在 consistent claim 上误报比例（对得住"减少噪声"叙事）
3. **成本**：
   - 平均 tokens / 篇
   - 平均延迟 / 篇（秒，CPU-only 标注）
   - **% claim 无需 LLM**（Tier 0+1 占比）
4. **鲁棒性**：F1 vs 扰动幅度 Δ 曲线
5. **消融**：
   - 去掉方向 B（只值优先）→ 看 precision 掉多少
   - 去掉 Tier 2（纯规则）→ 看 recall 掉多少
   - 去掉自适应 tol → 看 FPR 涨多少

### 预期叙事
> NCG 以接近 B3（全文 LLM）的 F1，在 <X% 的 claim 上触发 LLM，
> 单篇成本降低 ~Y×，且 FPR 显著低于 B0/B1。零训练、CPU 可跑。

---

## 6. 实现计划（映射到代码）

阶段化，每步可独立 commit、可回归：

1. **增强表格解析**（`gate_data.py::_extract_tables`）
   - 识别行头/列头，构建 `cell_index` / `value_index`
   - 保持向后兼容（现有 `rows` 字段保留）
2. **Claim 抽取模块**（新 `app/services/claim_extract.py`）
   - 数字定位 + 上下文窗口 + metric/method/dataset 字典匹配
   - 输出 `Claim` 数据类（加入 `app/models.py`）
3. **接地 + 判定**（新 `app/checks/claim_grounding.py` 或并入 gate_data）
   - Tier 0 双向规则、Tier 1 关系算术
   - Tier 2 LLM 裁决（复用 `services/llm.py::llm_check`，局部 prompt）
4. **接入 gate_data**：替换 `_check_text_table_consistency`，输出带 evidence 的 Issue
5. **Benchmark 脚手架**（`research/bench/`）
   - `build_corpus.py`：拉取/整理 arXiv 源码
   - `perturb.py`：P1–P4 扰动生成 + 标签
   - `run_eval.py`：跑 B0–B3 + Ours，出指标表
6. **消融 + 画图**（`research/bench/analyze.py`）

---

## 7. 命名候选（待定）
- **NCG** — Numerical Claim Grounding（本文暂用，中性、准确）
- **TabGround** — Table-grounded numerical verification（好记）
- **CiteYourTable** — 呼应 CiteAudit 的口吻（活泼）
- 建议正式定名前查重（arXiv 搜索）。

## 8. 风险与 limitations（写进 paper）
- Silver-label 假设原论文正确 → 少量噪声，需声明并可抽样人工校验一小批。
- 表格解析对复杂 multirow/multicolumn 有限 → 报告解析覆盖率。
- 作用域抽取依赖字典 → 对新指标名可能漏；Tier 2 兜底。
- 非母语/领域差异不影响本方法（纯数值+结构，无语言风格依赖）——相对 writing gate 是优势。
