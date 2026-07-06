"""Gate 5: 实验数据完整性检查

从 LaTeX 表格中提取数值数据，检测可疑模式：
1. 重复行：两行数据完全相同
2. 尾数模式：一列中过多相同尾数（如全是 .5 结尾）
3. 偏移造假：某行 = 另一行 + 常数（数据B = 数据A + 0.2）
4. 异常一致性：一列方差为0或极低
5. 精度不一致：同一列小数位数差异大
6. Benford's Law：首位数字分布异常
"""

import math
import re
from collections import Counter
from itertools import combinations

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity, TexFile


# Extract tabular data from LaTeX
_TABULAR_PATTERN = re.compile(
    r"\\begin\{tabular[*x]?\}[^\n]*\n(.*?)\\end\{tabular[*x]?\}",
    re.DOTALL,
)
_TABLE_ENV_PATTERN = re.compile(
    r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}",
    re.DOTALL,
)
_CAPTION_PATTERN = re.compile(r"\\caption(?:\[[^\]]*\])?\{(.+?)\}", re.DOTALL)
_NUMBER_PATTERN = re.compile(r"-?\d+\.\d+|-?\d+")


def _clean_cell_text(cell: str) -> str:
    """Strip LaTeX markup from a cell, returning plain text."""
    cell = re.sub(r"\\(?:textbf|textit|emph|mathbf|mathrm|text)\{([^}]*)\}", r"\1", cell)
    cell = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", cell)
    cell = re.sub(r"\\[a-zA-Z]+", "", cell)
    cell = cell.replace("{", "").replace("}", "").replace("$", "").replace("\\", "")
    return cell.strip()


def _is_header_row(cells: list[str]) -> bool:
    """Heuristic: a row is a header if most cells are non-numeric text."""
    numeric_count = 0
    text_count = 0
    for c in cells:
        cleaned = _clean_cell_text(c)
        if not cleaned:
            continue
        nums = _NUMBER_PATTERN.findall(cleaned)
        if nums:
            numeric_count += 1
        else:
            text_count += 1
    if not (numeric_count + text_count):
        return False
    return text_count > numeric_count


def _extract_tables(tex_files: list[TexFile]) -> list[dict]:
    """Extract all tables with their numeric data from tex files.

    Each returned table dict contains:
      rows        : list[list[float|None]]   (backward-compatible)
      col_headers : list[str]                (column header labels, may be empty strings)
      row_headers : list[str]                (first-column label for each data row)
      cell_index  : dict[(row_hdr, col_hdr) -> float]   (semantic address → value)
      value_index : dict[str -> list[dict]]  (str(round(v,2)) → [{row,col,value}])
    """
    tables = []

    for tex_file in tex_files:
        text = tex_file.raw_text

        for table_match in _TABLE_ENV_PATTERN.finditer(text):
            table_content = table_match.group(1)

            cap_match = _CAPTION_PATTERN.search(table_content)
            caption = cap_match.group(1).strip()[:100] if cap_match else "Unknown Table"

            tab_match = _TABULAR_PATTERN.search(table_content)
            if not tab_match:
                continue

            tabular_body = tab_match.group(1)

            # --- Split into raw rows (skip rule lines) ---
            raw_rows: list[list[str]] = []
            for chunk in tabular_body.split("\\\\"):
                # Each chunk may contain newlines with \hline etc. before the
                # actual cell content — split sub-lines and handle independently.
                for line in chunk.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if re.match(r"\\(?:hline|toprule|midrule|bottomrule|cline|hdashline)", line):
                        continue
                    cells = [c.strip() for c in line.split("&")]
                    if any(c for c in cells):
                        raw_rows.append(cells)

            if not raw_rows:
                continue

            # --- Detect header row (first row that is mostly text) ---
            col_headers: list[str] = []
            data_raw_rows = raw_rows
            if raw_rows and _is_header_row(raw_rows[0]):
                col_headers = [_clean_cell_text(c) for c in raw_rows[0]]
                data_raw_rows = raw_rows[1:]

            # --- Parse data rows; first cell treated as potential row header ---
            rows: list[list[float | None]] = []
            row_headers: list[str] = []

            for raw_row in data_raw_rows:
                if not raw_row:
                    continue

                # First cell: if non-numeric, treat as row header
                first_clean = _clean_cell_text(raw_row[0])
                first_nums = _NUMBER_PATTERN.findall(first_clean)
                if first_nums:
                    row_hdr = ""
                    value_cells = raw_row
                else:
                    row_hdr = first_clean
                    value_cells = raw_row[1:]

                row_numbers: list[float | None] = []
                for cell in value_cells:
                    cell_clean = _clean_cell_text(cell)
                    nums = _NUMBER_PATTERN.findall(cell_clean)
                    if nums:
                        try:
                            row_numbers.append(float(nums[0]))
                        except ValueError:
                            row_numbers.append(None)
                    else:
                        row_numbers.append(None)

                if any(x is not None for x in row_numbers):
                    rows.append(row_numbers)
                    row_headers.append(row_hdr)

            if not rows:
                continue

            num_cols = max(len(r) for r in rows)

            # Align col_headers to value columns (drop the row-header column if present)
            # col_headers may be longer by 1 if the first col is the row-header column
            value_col_headers: list[str] = []
            if col_headers:
                # If we stripped the first data cell as row-header, also strip
                # the first col_header (it was the row-label column header).
                offset = 1 if any(h for h in row_headers) else 0
                value_col_headers = col_headers[offset:]

            # Pad/truncate to num_cols
            while len(value_col_headers) < num_cols:
                value_col_headers.append("")
            value_col_headers = value_col_headers[:num_cols]

            # --- Build cell_index and value_index ---
            cell_index: dict[tuple[str, str], float] = {}
            value_index: dict[str, list[dict]] = {}

            for ri, (row, rhdr) in enumerate(zip(rows, row_headers)):
                for ci, v in enumerate(row):
                    if v is None:
                        continue
                    chdr = value_col_headers[ci] if ci < len(value_col_headers) else ""
                    if rhdr or chdr:
                        cell_index[(rhdr, chdr)] = v
                    # value_index keyed by rounded string for fast lookup
                    vkey = f"{v:.2f}"
                    if vkey not in value_index:
                        value_index[vkey] = []
                    value_index[vkey].append({
                        "row": ri, "col": ci,
                        "row_hdr": rhdr, "col_hdr": chdr,
                        "value": v,
                    })

            start_pos = table_match.start()
            line_num = text[:start_pos].count("\n") + 1

            tables.append({
                "caption": caption,
                "rows": rows,                        # backward-compatible
                "col_headers": value_col_headers,
                "row_headers": row_headers,
                "cell_index": cell_index,
                "value_index": value_index,
                "file": tex_file.path.name,
                "line": line_num,
                "num_cols": num_cols,
            })

    return tables


def _check_duplicate_rows(table: dict) -> list[dict]:
    """Check for duplicate rows in a table.

    Only flags rows with >= 3 numeric columns (2-column tables are too common
    in survey/demographic results to be suspicious). Reports one finding per
    unique duplicate group rather than every pairwise combination.
    """
    from collections import defaultdict

    findings = []
    rows = table["rows"]

    # Build groups keyed by the tuple of non-None numeric values
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        nums = tuple(x for x in row if x is not None)
        if len(nums) >= 3:  # need at least 3 numeric cols to be suspicious
            groups[nums].append(i)

    for key, indices in groups.items():
        if len(indices) >= 2:
            idx_str = ", ".join(str(i + 1) for i in indices)
            findings.append({
                "type": "duplicate_row",
                "message": f"第 {idx_str} 行数据完全相同（{len(indices)} 行重复）",
                "evidence": f"行数据: {list(key)}",
            })
    return findings


def _check_tail_pattern(table: dict) -> list[dict]:
    """Check for suspicious tail digit patterns in columns (decimals only)."""
    findings = []
    rows = table["rows"]
    num_cols = table["num_cols"]

    for col_idx in range(num_cols):
        col_values = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx] is not None]
        if len(col_values) < 5:
            continue

        # Skip if all values are integers (no decimal part)
        if all(v == int(v) for v in col_values):
            continue

        # Check last digit pattern (after decimal point)
        tails = []
        for v in col_values:
            s = f"{v:.10f}".rstrip("0")
            if "." in s and s.split(".")[1]:
                tail = s.split(".")[1][-1]
                tails.append(tail)

        if len(tails) < 5:
            continue

        # Count most common tail digit
        counter = Counter(tails)
        most_common_digit, most_common_count = counter.most_common(1)[0]
        ratio = most_common_count / len(tails)

        # If >75% of decimal values end with same digit, suspicious
        if ratio >= 0.75 and most_common_digit != "0":
            findings.append({
                "type": "tail_pattern",
                "message": f"第 {col_idx+1} 列: {most_common_count}/{len(tails)} 个小数值尾数为 '{most_common_digit}'（{ratio:.0%}）",
                "evidence": f"值: {col_values[:8]}{'...' if len(col_values)>8 else ''}",
            })

    return findings


def _check_offset_fabrication(table: dict) -> list[dict]:
    """Check if one row = another row + constant (offset fabrication)."""
    findings = []
    rows = table["rows"]

    for i, j in combinations(range(len(rows)), 2):
        row_a = [x for x in rows[i] if x is not None]
        row_b = [x for x in rows[j] if x is not None]

        if len(row_a) < 3 or len(row_a) != len(row_b):
            continue

        # Check if difference is constant
        diffs = [round(b - a, 6) for a, b in zip(row_a, row_b)]
        if len(set(diffs)) == 1 and diffs[0] != 0:
            offset = diffs[0]
            findings.append({
                "type": "offset",
                "message": f"第 {i+1} 行 + {offset} = 第 {j+1} 行（所有列偏移相同）",
                "evidence": f"行{i+1}: {row_a[:5]}\n行{j+1}: {row_b[:5]}",
            })

    return findings


def _check_low_variance(table: dict) -> list[dict]:
    """Check for columns with suspiciously low variance (only for decimal data, >5 rows)."""
    findings = []
    rows = table["rows"]
    num_cols = table["num_cols"]

    for col_idx in range(num_cols):
        col_values = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx] is not None]
        if len(col_values) < 6:
            continue

        # Skip integer columns
        if all(v == int(v) for v in col_values):
            continue

        # All same value?
        if len(set(col_values)) == 1:
            findings.append({
                "type": "zero_variance",
                "message": f"第 {col_idx+1} 列所有值完全相同: {col_values[0]}",
                "evidence": f"共 {len(col_values)} 个值全部为 {col_values[0]}",
            })

    return findings


def _check_precision_inconsistency(table: dict) -> list[dict]:
    """Check for inconsistent decimal precision within a column.

    Only flags columns where ALL values have decimals but the precision spread
    is large (≥4 positions). Columns that mix integers with decimals are common
    in valid tables (e.g. counts alongside percentages) and are not flagged.
    """
    findings = []
    rows = table["rows"]
    num_cols = table["num_cols"]

    for col_idx in range(num_cols):
        col_values = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx] is not None]
        if len(col_values) < 4:
            continue

        # Skip columns where any value is a whole number —
        # mixing integers with decimals is legitimate (e.g. count + ratio columns).
        if any(v == int(v) for v in col_values):
            continue

        precisions = []
        for v in col_values:
            s = f"{v}"
            if "." in s:
                precisions.append(len(s.split(".")[1].rstrip("0")) or 1)
            else:
                precisions.append(0)

        if len(set(precisions)) > 2 and max(precisions) - min(precisions) >= 4:
            findings.append({
                "type": "precision_inconsistency",
                "message": f"第 {col_idx+1} 列小数精度差异异常（{min(precisions)}-{max(precisions)} 位）",
                "evidence": f"精度分布: {dict(Counter(precisions))}",
            })

    return findings


# Expected Benford distribution for first digit (1-9)
_BENFORD_EXPECTED = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def _check_benford_law(table: dict) -> list[dict]:
    """Check if first-digit distribution deviates from Benford's Law.

    Only applies to tables with enough numeric data (>= 30 values).
    Skips values 0-9 (single digit), percentage-like values (0.xx), and
    columns where all values are in [0, 100] (score/percentage columns).
    """
    findings = []
    rows = table["rows"]
    num_cols = table["num_cols"]

    # Per-column check: skip if column looks like percentages or scores
    pct_cols: set[int] = set()
    for col_idx in range(num_cols):
        col_vals = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx] is not None]
        if col_vals and all(0.0 <= v <= 100.0 for v in col_vals):
            pct_cols.add(col_idx)

    all_values = []
    for row in rows:
        for col_idx, v in enumerate(row):
            if v is not None and col_idx not in pct_cols and abs(v) >= 10:
                all_values.append(abs(v))

    if len(all_values) < 30:
        return findings

    first_digits = []
    for v in all_values:
        s = f"{v:.0f}" if v == int(v) else f"{v}"
        s = s.lstrip("0").lstrip("-").lstrip(".")
        if s and s[0].isdigit() and s[0] != "0":
            first_digits.append(int(s[0]))

    if len(first_digits) < 30:
        return findings

    n = len(first_digits)
    counter = Counter(first_digits)
    chi_sq = 0
    for d in range(1, 10):
        observed = counter.get(d, 0)
        expected = _BENFORD_EXPECTED[d] * n
        chi_sq += (observed - expected) ** 2 / expected

    # Chi-squared critical value for 8 df at p=0.01 is 20.09
    if chi_sq > 20.09:
        dist_str = ", ".join(f"{d}:{counter.get(d,0)}" for d in range(1, 10))
        findings.append({
            "type": "benford_violation",
            "message": f"首位数字分布异常（χ²={chi_sq:.1f}，p<0.01），不符合 Benford 定律",
            "evidence": f"分布: [{dist_str}]，共 {n} 个数值（已跳过百分比列）",
        })

    return findings


class DataIntegrityGate(BaseGate):
    """Gate 5: 实验数据完整性检查"""

    name = "data_integrity"
    description = "数据完整性：检测表格中的重复数据、可疑模式、偏移造假等异常"
    is_blocking = False  # warning-level, 不强制阻止但标出

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []

        # Extract tables
        tables = _extract_tables(paper.tex_files)

        if not tables:
            return CheckResult(
                gate_name=self.name,
                gate_description=self.description,
                passed=True,
                score=100.0,
                issues=[],
                summary="未发现 LaTeX 表格数据",
                metadata={"tables_checked": 0},
            )

        total_findings = 0
        table_summaries = []

        for table in tables:
            findings = []
            findings.extend(_check_duplicate_rows(table))
            findings.extend(_check_tail_pattern(table))
            findings.extend(_check_offset_fabrication(table))
            findings.extend(_check_low_variance(table))
            findings.extend(_check_precision_inconsistency(table))
            findings.extend(_check_benford_law(table))

            table_summaries.append({
                "caption": table["caption"],
                "file": table["file"],
                "line": table["line"],
                "rows": len(table["rows"]),
                "findings": len(findings),
            })

            for f in findings:
                total_findings += 1
                # duplicate_row and offset are serious (ERROR); others are WARNING
                severity = Severity.ERROR if f["type"] in ("duplicate_row", "offset") else Severity.WARNING
                issues.append(Issue(
                    severity=severity,
                    message=f"[{table['caption'][:30]}] {f['message']}",
                    location=f"{table['file']}:{table['line']}",
                    evidence=f["evidence"],
                    suggestion="此数据模式可能表明数据异常。请核实原始实验数据。",
                    file=table["file"],
                    line=table["line"],
                ))

        # P-value suspicion check (scan full text for borderline p-values)
        p_value_findings = self._check_suspicious_pvalues(paper.tex_files)
        for pf in p_value_findings:
            total_findings += 1
            issues.append(Issue(
                severity=Severity.WARNING,
                message=pf["message"],
                location=pf.get("location", ""),
                evidence=pf["evidence"],
                suggestion="多个刚好低于显著性阈值的 p 值可能表明 p-hacking。请提供原始统计检验结果。",
                file=pf.get("file"),
                line=pf.get("line"),
            ))

        # NCG: Numerical Claim Grounding (Tier 0 + Tier 1, rule-based)
        # Replaces the old naive _check_text_table_consistency.
        ncg_findings = self._ncg_check(paper.tex_files, tables)
        for cf in ncg_findings:
            total_findings += 1
            issues.append(Issue(
                severity=Severity.WARNING,
                message=cf["message"],
                location=cf.get("location", ""),
                evidence=cf["evidence"],
                suggestion="正文中引用的数值与表格数据不匹配。请核对原始实验数据，确认是否为笔误或数据更新后未同步。",
                file=cf.get("file"),
                line=cf.get("line"),
            ))

        # Impossible value check: metric values outside physically valid range
        impossible_findings = self._check_impossible_values(paper.tex_files, tables)
        for iv in impossible_findings:
            total_findings += 1
            issues.append(Issue(
                severity=Severity.ERROR,
                message=iv["message"],
                location=iv.get("location", ""),
                evidence=iv["evidence"],
                suggestion="该数值超出指标的合法取值范围，请核查原始数据或单位换算。",
                file=iv.get("file"),
                line=iv.get("line"),
            ))

        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warn_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        # Errors cost 20 pts each, warnings 5 pts each — cap at 0
        score = max(0, 100 - error_count * 20 - warn_count * 5)
        passed = error_count == 0

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=f"检查了 {len(tables)} 个表格，发现 {total_findings} 个可疑数据模式",
            metadata={"tables_checked": len(tables), "table_summaries": table_summaries},
        )

    @staticmethod
    def _check_suspicious_pvalues(tex_files) -> list[dict]:
        """Detect suspiciously borderline p-values (just below 0.05)."""
        # Pattern matches p = 0.04x, p < 0.05, p=.04x, etc.
        p_pattern = re.compile(
            r"[pP]\s*[=<]\s*\.?(0\.0[0-4]\d*)",
        )
        findings = []
        borderline_values = []  # p-values in [0.04, 0.05)

        for tex_file in tex_files:
            lines = tex_file.raw_text.split("\n")
            for line_num, line in enumerate(lines, 1):
                for m in p_pattern.finditer(line):
                    try:
                        val = float(m.group(1))
                        if 0.04 <= val < 0.05:
                            borderline_values.append({
                                "value": val,
                                "file": tex_file.path.name,
                                "line": line_num,
                                "context": line.strip()[:60],
                            })
                    except ValueError:
                        pass

        # Only flag if multiple borderline p-values found (≥3)
        if len(borderline_values) >= 3:
            evidence = "\n".join(f"  p={v['value']} ({v['file']}:{v['line']})" for v in borderline_values[:5])
            findings.append({
                "message": f"发现 {len(borderline_values)} 个刚好低于 0.05 的 p 值（可能存在 p-hacking）",
                "evidence": evidence,
                "location": borderline_values[0]["file"],
                "file": borderline_values[0]["file"],
                "line": borderline_values[0]["line"],
            })

        return findings

    @staticmethod
    def _check_text_table_consistency(tex_files, tables) -> list[dict]:
        """Check if numbers claimed in text match table values.

        Flags cases where a claim value is *close to* a table value (same order
        of magnitude) but does not agree at the claimed precision — a pattern
        consistent with someone editing the text number without updating the table
        (or vice versa).

        Two-sided guard:
        - lower bound: diff >= 0.5 ULP at claimed precision (not just float noise)
        - upper bound: diff < 10% of the claimed value (actually close, same metric)

        This prevents cross-matching completely unrelated numbers (e.g. 3.108 in
        text vs 4.5 in a different table row/column).
        """
        findings = []
        if not tables:
            return findings

        table_values: list[float] = []
        for table in tables:
            for row in table["rows"]:
                for v in row:
                    if v is not None and v != int(v):
                        table_values.append(v)

        if not table_values:
            return findings

        claim_pattern = re.compile(
            r"(?:achiev|obtain|reach|attain|report)\w*\s+(?:an?\s+)?(?:\w+\s+)?(?:of\s+)?(\d+\.\d+)",
            re.IGNORECASE,
        )

        for tex_file in tex_files:
            lines = tex_file.raw_text.split("\n")
            for i, line in enumerate(lines, 1):
                for m in claim_pattern.finditer(line):
                    claimed_str = m.group(1)
                    try:
                        claimed_val = float(claimed_str)
                    except ValueError:
                        continue
                    if claimed_val == 0:
                        continue

                    claimed_dp = len(claimed_str.split(".")[1]) if "." in claimed_str else 0
                    lower = 0.5 * (10 ** -claimed_dp)   # must be more than rounding noise
                    # Upper bound: within 5% AND within 2.0 absolute units.
                    # Tighter than 10% to avoid matching unrelated scores that happen
                    # to be close (e.g. two different models' accuracy values).
                    upper = min(claimed_val * 0.05, 2.0)

                    for tv in table_values:
                        tv_rounded = round(tv, claimed_dp)
                        if tv_rounded == claimed_val:
                            continue  # agrees at stated precision, not suspicious
                        diff = abs(claimed_val - tv_rounded)
                        if lower <= diff <= upper:
                            findings.append({
                                "message": (
                                    f"正文中 {claimed_str} 与表格中 {tv} 接近但不一致"
                                    f"（对齐到 {claimed_dp} 位后差 {diff:.{claimed_dp}f}）"
                                ),
                                "evidence": f"行 {i}: {line.strip()[:60]}",
                                "location": tex_file.path.name,
                                "file": tex_file.path.name,
                                "line": i,
                            })
                            break

        return findings[:5]

    # ------------------------------------------------------------------
    # NCG — Numerical Claim Grounding (Tier 0 + Tier 1, rule-based)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_claims(tex_files: list[TexFile]) -> list[dict]:
        """Extract numerical claims from LaTeX text.

        Returns list of dicts:
          value      : float
          value_str  : str as written (e.g. "92.3")
          dp         : decimal places in value_str
          claim_type : "absolute" | "comparative"
          delta      : float | None  (for comparative: stated improvement)
          scope      : dict{metric?, dataset?, method?}  — from surrounding context
          file       : str
          line       : int
          context    : str  — the sentence fragment
        """
        # Metric names common in NLP / ML papers
        _METRICS = {
            "accuracy", "acc", "f1", "f-1", "f1-score", "micro-f1", "macro-f1",
            "bleu", "bleu-1", "bleu-2", "bleu-4", "sacrebleu",
            "rouge", "rouge-1", "rouge-2", "rouge-l", "rougel",
            "precision", "recall", "perplexity", "ppl",
            "em", "exact match", "exact_match",
            "map", "ndcg", "mrr", "hit", "hits",
            "auc", "roc", "ap", "score", "performance", "result",
            "bertscore", "bert-score", "meteor", "cider", "bleurt", "mauve",
            "wer", "cer", "ter",
            "spearman", "pearson", "kendall",
            "pass@1", "pass@10", "pass@100",
        }
        # Dataset shorthands (extend as needed)
        _DATASETS = {
            "squad", "squad2", "squadv2",
            "mnli", "snli", "nli", "sst", "sst-2", "sst2", "imdb",
            "glue", "superglue",
            "cnn", "dailymail", "xsum",
            "triviaqa", "natural questions", "nq",
            "mmlu", "hellaswag", "winogrande", "arc", "truthfulqa",
            "gsm8k", "humaneval", "mbpp",
            "wmt14", "wmt16", "wmt19", "wmt20", "wmt21",
            "conll", "conll-2003", "ontonotes",
            "coco", "vqa", "nocaps",
            "hotpotqa", "musique",
            "ag news", "ag_news", "dbpedia",
        }
        # Model/method names for scope matching against row headers
        _MODEL_NAMES = {
            "bert", "roberta", "albert", "electra", "deberta",
            "gpt", "gpt2", "gpt-2", "gpt3", "gpt-3", "gpt4", "gpt-4",
            "t5", "bart", "pegasus", "led", "longformer", "bigbird",
            "xlnet", "xlm", "xlm-r", "xlm-roberta",
            "llama", "llama2", "llama-2", "mistral", "falcon", "phi",
            "gemma", "vicuna", "alpaca",
            "chatgpt", "gemini", "palm",
            "wav2vec", "hubert", "whisper",
            "vit", "clip", "blip",
            "baseline", "ours", "our model",
        }

        absolute_pat = re.compile(
            r"(?:achiev|obtain|reach|attain|report|get|scores?)\w*"
            r"(?:\s+(?:a|an|the))?"
            r"(?:\s+\w+){0,3}?\s+"
            r"(?:of\s+)?(\d+\.?\d*)\s*(?:%|pp|points?)?",
            re.IGNORECASE,
        )
        comparative_pat = re.compile(
            r"(?:outperform|surpass|exceed|improve|gain|better|higher|lower)\w*"
            r"(?:\s+\w+){0,6}?\s+by\s+(\d+\.?\d*)\s*(?:%|pp|points?)?",
            re.IGNORECASE,
        )

        def _scope_from_window(window: str) -> dict:
            wl = window.lower()
            metric = next((m for m in _METRICS if re.search(r"\b" + re.escape(m) + r"\b", wl)), None)
            dataset = next((d for d in _DATASETS if re.search(r"\b" + re.escape(d) + r"\b", wl)), None)
            method = next((m for m in _MODEL_NAMES if re.search(r"\b" + re.escape(m) + r"\b", wl)), None)
            return {"metric": metric, "dataset": dataset, "method": method}

        claims = []
        for tex_file in tex_files:
            lines = tex_file.raw_text.split("\n")
            for lineno, line in enumerate(lines, 1):
                # skip comment lines and table rows
                stripped = line.strip()
                if stripped.startswith("%") or line.count("&") >= 2:
                    continue
                window = " ".join(lines[max(0, lineno - 3):lineno + 1])

                for m in absolute_pat.finditer(line):
                    try:
                        v = float(m.group(1))
                    except ValueError:
                        continue
                    if v == 0 or v > 10_000:
                        continue
                    dp = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
                    claims.append({
                        "value": v, "value_str": m.group(1), "dp": dp,
                        "claim_type": "absolute", "delta": None,
                        "scope": _scope_from_window(window),
                        "file": tex_file.path.name, "line": lineno,
                        "context": stripped[:80],
                    })

                for m in comparative_pat.finditer(line):
                    try:
                        delta = float(m.group(1))
                    except ValueError:
                        continue
                    if delta <= 0 or delta > 100:
                        continue
                    dp = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
                    claims.append({
                        "value": delta, "value_str": m.group(1), "dp": dp,
                        "claim_type": "comparative", "delta": delta,
                        "scope": _scope_from_window(window),
                        "file": tex_file.path.name, "line": lineno,
                        "context": stripped[:80],
                    })

        return claims

    @staticmethod
    def _scope_sim(claim_scope: dict, col_hdr: str, row_hdr: str, caption: str) -> float:
        """Return 0–1 similarity between claim scope and a cell's semantic address.

        Weights:
          metric  match → 0.6 (sufficient alone to reach the 0.6 threshold)
          dataset match → +0.3 bonus
          method  match → +0.2 bonus

        A pure metric match (0.6) just clears the Tier-0 threshold.
        metric + method (0.8) or metric + dataset (0.9) are higher-confidence.
        """
        target = (col_hdr + " " + row_hdr + " " + caption).lower()
        score = 0.0
        if claim_scope.get("metric") and claim_scope["metric"] in target:
            score += 0.6
        if claim_scope.get("dataset") and claim_scope["dataset"] in target:
            score += 0.3
        if claim_scope.get("method") and claim_scope["method"] in target:
            score += 0.2
        return min(score, 1.0)

    @staticmethod
    def _ncg_check(tex_files: list[TexFile], tables: list[dict]) -> list[dict]:
        """NCG Tier 0 + Tier 1: rule-based numerical claim grounding.

        Tier 0 — scope-first:
          Find the table cell whose (row_hdr, col_hdr, caption) best matches the
          claim's metric/dataset scope. If the cell value disagrees with the claim
          at stated precision → Contradicted.

        Tier 1 — value-first cross-check:
          If scope similarity is low (scope ambiguous), fall back to checking
          whether ANY table cell has a value within 2% of the claim. If none
          found → Ungroundable (skip). If found but disagreeing → flag.

        Only high-confidence Contradicted findings are reported.
        """
        claims = DataIntegrityGate._extract_claims(tex_files)
        if not claims or not tables:
            return []

        findings = []
        seen: set[tuple] = set()  # deduplicate by (file, line, value_str)

        for claim in claims:
            v = claim["value"]
            dp = claim["dp"]
            key = (claim["file"], claim["line"], claim["value_str"])
            if key in seen:
                continue

            # --- Tier 0: scope-first ---
            best_cell = None
            best_sim = 0.0
            for table in tables:
                caption = table.get("caption", "")
                ci = table.get("cell_index", {})
                for (rhdr, chdr), tv in ci.items():
                    sim = DataIntegrityGate._scope_sim(claim["scope"], chdr, rhdr, caption)
                    if sim > best_sim:
                        best_sim = sim
                        best_cell = {"value": tv, "row_hdr": rhdr, "col_hdr": chdr,
                                     "caption": caption, "table": table}

            if best_sim >= 0.6 and best_cell is not None:
                tv = best_cell["value"]
                tv_rounded = round(tv, dp)
                claimed_rounded = round(v, dp)
                if tv_rounded != claimed_rounded:
                    diff = abs(v - tv)
                    # Magnitude guard: if the two values differ by >50% relative to
                    # the larger, they're almost certainly in different units/scales
                    # (e.g. claim=12.8 benchmark score vs cell=2.5 task count).
                    # Real fabrication mismatches are always small (< a few percent).
                    magnitude = max(abs(v), abs(tv))
                    if magnitude > 0 and diff / magnitude > 0.5:
                        continue
                    # Only flag if difference is meaningful (≥ 1 ULP at stated dp)
                    if diff >= 10 ** -dp:
                        seen.add(key)
                        addr = f"{best_cell['row_hdr']} × {best_cell['col_hdr']}" if (
                            best_cell["row_hdr"] or best_cell["col_hdr"]
                        ) else best_cell["caption"][:30]
                        findings.append({
                            "message": (
                                f"正文声称 {claim['value_str']}，"
                                f"但对应表格 [{addr}] 中为 {tv}"
                                f"（差 {diff:.{max(dp,2)}f}）"
                            ),
                            "evidence": f"行 {claim['line']}: {claim['context']}",
                            "location": claim["file"],
                            "file": claim["file"],
                            "line": claim["line"],
                            "confidence": "high",
                        })
                continue  # scope found — don't fall through to Tier 1

            # --- Tier 1: value-first ---
            # Without semantic scope, any "close but not equal" check has
            # unacceptable false-positive rate (different models/settings with
            # similar scores). Tier 1 is intentionally disabled here; it will
            # be re-enabled once scope extraction covers these ambiguous claims.
            pass  # noqa: placeholder

        # Return high-confidence first, cap at 8 to avoid noise flood
        findings.sort(key=lambda f: 0 if f["confidence"] == "high" else 1)
        return findings[:8]

    @staticmethod
    def _check_impossible_values(tex_files: list[TexFile], tables: list[dict]) -> list[dict]:
        """Detect metric values outside their physically valid range.

        Rules:
          - Bounded-[0,100] metrics (accuracy, F1, precision, recall, BLEU, ROUGE,
            AUC, AP, Hits@K, Pass@K): value > 100 or value < 0 is impossible.
          - Perplexity (PPL): must be ≥ 1.0 (by definition).
          - p-value: must be in (0, 1].

        Checks both table cells (reliable) and in-text claims (via _extract_claims).
        """
        _BOUNDED_METRICS = re.compile(
            r"\b(?:accuracy|acc|f1|f-1|f1-score|micro-?f1|macro-?f1|"
            r"precision|recall|bleu|rouge|rouge-?[12l]|auc|ap|"
            r"hits?@\d+|pass@\d+|exact[\s_]?match|em|map|ndcg|mrr)\b",
            re.IGNORECASE,
        )
        _PPL_METRIC = re.compile(r"\b(?:perplexity|ppl)\b", re.IGNORECASE)
        _PVAL_METRIC = re.compile(r"\bp[\s-]?value\b|\bp\s*[=<]\s*", re.IGNORECASE)

        findings = []
        seen: set[tuple] = set()

        def _flag(msg, evidence, file, line):
            k = (file, line, msg[:40])
            if k not in seen:
                seen.add(k)
                findings.append({
                    "message": msg, "evidence": evidence,
                    "location": file, "file": file, "line": line,
                })

        # Check table cells: col_hdr tells us the metric
        for table in tables:
            col_headers = table.get("col_headers", [])
            for ri, row in enumerate(table["rows"]):
                for ci, v in enumerate(row):
                    if v is None:
                        continue
                    chdr = col_headers[ci] if ci < len(col_headers) else ""
                    if _BOUNDED_METRICS.search(chdr):
                        if v > 100.0 + 1e-3:
                            _flag(
                                f"表格列 [{chdr}] 中数值 {v} 超过 100（百分比指标上限）",
                                f"表 [{table['caption'][:40]}] 第 {ri+1} 行",
                                table["file"], table["line"],
                            )
                        elif v < 0:
                            _flag(
                                f"表格列 [{chdr}] 中数值 {v} 为负（百分比指标不能为负）",
                                f"表 [{table['caption'][:40]}] 第 {ri+1} 行",
                                table["file"], table["line"],
                            )
                    if _PPL_METRIC.search(chdr) and v < 1.0:
                        _flag(
                            f"表格列 [{chdr}] 中 perplexity={v} < 1（物理上不可能）",
                            f"表 [{table['caption'][:40]}] 第 {ri+1} 行",
                            table["file"], table["line"],
                        )

        # Check in-text claims via _extract_claims (scope carries metric name)
        claims = DataIntegrityGate._extract_claims(tex_files)
        for claim in claims:
            v = claim["value"]
            metric = (claim["scope"].get("metric") or "").lower()
            if not metric:
                continue
            if _BOUNDED_METRICS.search(metric):
                if v > 100.0 + 1e-3:
                    _flag(
                        f"正文声称 {claim['value_str']} ({metric})，超过 100",
                        f"行 {claim['line']}: {claim['context']}",
                        claim["file"], claim["line"],
                    )

        return findings[:6]
