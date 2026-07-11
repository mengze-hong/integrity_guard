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
                message=f"Undefined citation: \\cite{{{key}}} → will show '?' in compiled PDF",
                location=", ".join(locations),
                evidence=f"Key '{key}' is used in text but not defined in .bib",
                suggestion=f"Add a '{key}' entry to your .bib file, or fix the citation key spelling.",
            ))

        # Warning: orphan bib entries (not critical but messy)
        uncited_entries = sorted(bib_keys - all_cite_keys)
        for key in uncited_entries:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"Orphaned entry: '{key}' is defined in .bib but never cited",
                location="bib",
                suggestion=f"Either cite '{key}' in the text, or remove it from .bib.",
            ))

        # Check for duplicate bib keys
        seen: dict[str, int] = {}
        for entry in paper.bib_entries:
            seen[entry.key] = seen.get(entry.key, 0) + 1
        for key, count in sorted(seen.items()):
            if count > 1:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"Duplicate key: '{key}' is defined {count} times in .bib",
                    location="bib",
                    suggestion="Each citation key must be unique. Rename one of the duplicates.",
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
                    message=f"[{entry.key}] missing required fields: {', '.join(missing)}",
                    location=f"bib:{entry.key}",
                    suggestion="A complete bib entry needs at least title, author, and year.",
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
                f"{total_cites} citation keys: {valid_cites} OK, "
                f"{len(undefined_cites)} undefined (→ '?'), "
                f"{len(uncited_entries)} orphaned"
            ),
            metadata={
                "total_citations": total_cites,
                "undefined_count": len(undefined_cites),
                "orphan_count": len(uncited_entries),
            },
        )
