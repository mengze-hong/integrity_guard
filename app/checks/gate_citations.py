"""Gate 3: Citation-Bibliography Consistency.

CRITICAL: Every \\cite{key} in .tex MUST have a corresponding .bib entry.
Missing entries cause '?' marks in compiled PDF — this is a desk-reject level issue.

Also checks:
- Orphan .bib entries (defined but never cited)
- Duplicate citation keys
"""

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity


class CitationConsistencyGate(BaseGate):
    """Gate 3: Every cite key must exist in .bib. Zero tolerance."""

    name = "citation_bib_consistency"
    description = "引用键匹配：检查每个 \\cite{key} 是否都能在 .bib 中找到（找不到 = PDF 显示问号 [?] = desk reject）"
    is_blocking = True

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []

        # Collect ALL citation keys from ALL .tex files (with their locations)
        cite_locations: dict[str, list[str]] = {}  # key → [file:line info]
        for tex_file in paper.tex_files:
            for key in tex_file.citations:
                if key not in cite_locations:
                    cite_locations[key] = []
                cite_locations[key].append(str(tex_file.path.name))

        all_cite_keys = set(cite_locations.keys())
        bib_keys = {entry.key for entry in paper.bib_entries}

        # CRITICAL CHECK: undefined citations → '?' in PDF
        undefined_cites = sorted(all_cite_keys - bib_keys)
        for key in undefined_cites:
            locations = cite_locations[key]
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"未定义引用: \\cite{{{key}}} → 编译后 PDF 中将显示 '?'",
                location=", ".join(locations),
                evidence=f"引用键 '{key}' 在正文中使用但在 .bib 中不存在",
                suggestion=f"请在 .bib 中添加 '{key}' 条目，或修正引用键的拼写。",
            ))

        # Warning: orphan bib entries (not critical but messy)
        uncited_entries = sorted(bib_keys - all_cite_keys)
        for key in uncited_entries:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"孤立条目: '{key}' 在 .bib 中定义但从未被引用",
                location="bib",
                suggestion=f"请在正文中引用 '{key}'，或从 .bib 中删除该条目。",
            ))

        # Check for duplicate bib keys
        seen: dict[str, int] = {}
        for entry in paper.bib_entries:
            seen[entry.key] = seen.get(entry.key, 0) + 1
        for key, count in sorted(seen.items()):
            if count > 1:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"重复键: .bib 中 '{key}' 定义了 {count} 次",
                    location="bib",
                    suggestion="每个引用键必须唯一，请重命名其中一个。",
                ))

        # Check 4: Incomplete bib entries (missing critical fields)
        for entry in paper.bib_entries:
            missing = []
            if not entry.title:
                missing.append("title")
            if not entry.authors:
                missing.append("author")
            if not entry.year:
                missing.append("year")
            if missing:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"[{entry.key}] 缺少必要字段: {', '.join(missing)}",
                    location=f"bib:{entry.key}",
                    suggestion="完整的 bib 条目至少需要 title、author、year。缺少字段可能导致参考文献列表显示不完整。",
                ))

        # Score and pass/fail
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        total_cites = len(all_cite_keys)
        valid_cites = total_cites - len(undefined_cites)
        score = (valid_cites / total_cites * 100) if total_cites > 0 else 100.0
        passed = error_count == 0

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=(
                f"共 {total_cites} 个引用键: {valid_cites} 个正常, "
                f"{len(undefined_cites)} 个未定义 (→ '?'), "
                f"{len(uncited_entries)} 个孤立条目"
            ),
            metadata={
                "total_citations": total_cites,
                "undefined_count": len(undefined_cites),
                "orphan_count": len(uncited_entries),
            },
        )
