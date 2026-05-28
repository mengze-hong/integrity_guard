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


def _extract_tables(tex_files: list[TexFile]) -> list[dict]:
    """Extract all tables with their numeric data from tex files."""
    tables = []

    for tex_file in tex_files:
        text = tex_file.raw_text

        for table_match in _TABLE_ENV_PATTERN.finditer(text):
            table_content = table_match.group(1)

            # Get caption
            cap_match = _CAPTION_PATTERN.search(table_content)
            caption = cap_match.group(1).strip()[:100] if cap_match else "Unknown Table"

            # Find tabular inside
            tab_match = _TABULAR_PATTERN.search(table_content)
            if not tab_match:
                continue

            tabular_body = tab_match.group(1)
            # Parse rows
            rows = []
            for line in tabular_body.split("\\\\"):
                line = line.strip()
                if not line or line.startswith("\\hline") or line.startswith("\\toprule") or line.startswith("\\midrule") or line.startswith("\\bottomrule"):
                    continue
                # Split by & (LaTeX column separator)
                cells = [c.strip() for c in line.split("&")]
                # Extract numbers from each cell
                row_numbers = []
                for cell in cells:
                    # Remove LaTeX commands
                    cell_clean = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", cell)
                    cell_clean = re.sub(r"\\[a-zA-Z]+", "", cell_clean)
                    cell_clean = cell_clean.replace("{", "").replace("}", "").replace("$", "").replace("\\", "")
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

            if rows:
                # Get line number
                start_pos = table_match.start()
                line_num = text[:start_pos].count("\n") + 1
                tables.append({
                    "caption": caption,
                    "rows": rows,
                    "file": tex_file.path.name,
                    "line": line_num,
                    "num_cols": max(len(r) for r in rows),
                })

    return tables


def _check_duplicate_rows(table: dict) -> list[dict]:
    """Check for duplicate rows in a table."""
    findings = []
    rows = table["rows"]
    for i, j in combinations(range(len(rows)), 2):
        if rows[i] == rows[j] and any(x is not None for x in rows[i]):
            findings.append({
                "type": "duplicate_row",
                "message": f"第 {i+1} 行和第 {j+1} 行数据完全相同",
                "evidence": f"行数据: {[x for x in rows[i] if x is not None]}",
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
    """Check for inconsistent decimal precision within a column."""
    findings = []
    rows = table["rows"]
    num_cols = table["num_cols"]

    for col_idx in range(num_cols):
        col_values = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx] is not None]
        if len(col_values) < 3:
            continue

        # Count decimal places
        precisions = []
        for v in col_values:
            s = str(v)
            if "." in s:
                precisions.append(len(s.split(".")[1].rstrip("0")) or 0)
            else:
                precisions.append(0)

        unique_prec = set(precisions)
        if len(unique_prec) > 2 and max(precisions) - min(precisions) >= 3:
            findings.append({
                "type": "precision_inconsistency",
                "message": f"第 {col_idx+1} 列小数精度不一致（{min(precisions)}-{max(precisions)} 位）",
                "evidence": f"精度分布: {dict(Counter(precisions))}",
            })

    return findings


# Expected Benford distribution for first digit (1-9)
_BENFORD_EXPECTED = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def _check_benford_law(table: dict) -> list[dict]:
    """Check if first-digit distribution deviates from Benford's Law.

    Only applies to tables with enough numeric data (>= 30 values).
    Skips values 0-9 (single digit) and percentage-like values (0.xx).
    """
    findings = []
    rows = table["rows"]

    # Collect all numeric values across the table
    all_values = []
    for row in rows:
        for v in row:
            if v is not None and abs(v) >= 10:  # Only multi-digit numbers
                all_values.append(abs(v))

    if len(all_values) < 30:
        return findings

    # Extract first digits
    first_digits = []
    for v in all_values:
        s = f"{v:.0f}" if v == int(v) else f"{v}"
        s = s.lstrip("0").lstrip("-").lstrip(".")
        if s and s[0].isdigit() and s[0] != "0":
            first_digits.append(int(s[0]))

    if len(first_digits) < 30:
        return findings

    # Chi-squared test against Benford distribution
    n = len(first_digits)
    counter = Counter(first_digits)
    chi_sq = 0
    for d in range(1, 10):
        observed = counter.get(d, 0)
        expected = _BENFORD_EXPECTED[d] * n
        chi_sq += (observed - expected) ** 2 / expected

    # Chi-squared critical value for 8 degrees of freedom at p=0.01 is 20.09
    if chi_sq > 20.09:
        # Build distribution summary
        dist_str = ", ".join(f"{d}:{counter.get(d,0)}" for d in range(1, 10))
        findings.append({
            "type": "benford_violation",
            "message": f"首位数字分布异常（χ²={chi_sq:.1f}，p<0.01），不符合 Benford 定律",
            "evidence": f"分布: [{dist_str}]，共 {n} 个数值",
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

        # Text-table number consistency check
        consistency_findings = self._check_text_table_consistency(paper.tex_files, tables)
        for cf in consistency_findings:
            total_findings += 1
            issues.append(Issue(
                severity=Severity.WARNING,
                message=cf["message"],
                location=cf.get("location", ""),
                evidence=cf["evidence"],
                suggestion="正文中引用的数值与表格数据不一致。请核对后修正。",
                file=cf.get("file"),
                line=cf.get("line"),
            ))

        score = max(0, 100 - total_findings * 15)
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
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
        """Check if numbers claimed in text match table values."""
        findings = []
        if not tables:
            return findings

        # Collect all decimal numbers from tables
        table_numbers = set()
        for table in tables:
            for row in table["rows"]:
                for v in row:
                    if v is not None and v != int(v):
                        table_numbers.add(f"{v:.2f}")
                        table_numbers.add(f"{v:.1f}")

        if not table_numbers:
            return findings

        # Search for "achieve/obtain X" patterns in text
        claim_pattern = re.compile(
            r"(?:achiev|obtain|reach|attain|report)\w*\s+(?:an?\s+)?(?:\w+\s+)?(?:of\s+)?(\d+\.\d+)",
            re.IGNORECASE
        )

        for tex_file in tex_files:
            lines = tex_file.raw_text.split("\n")
            for i, line in enumerate(lines, 1):
                for m in claim_pattern.finditer(line):
                    claimed = m.group(1)
                    for tn in table_numbers:
                        try:
                            diff = abs(float(claimed) - float(tn))
                            if 0.001 < diff < 0.02:
                                findings.append({
                                    "message": f"正文中 {claimed} 与表格中 {tn} 不一致（差 {diff:.3f}）",
                                    "evidence": f"行 {i}: {line.strip()[:60]}",
                                    "location": tex_file.path.name,
                                    "file": tex_file.path.name,
                                    "line": i,
                                })
                                break
                        except ValueError:
                            pass

        return findings[:3]
