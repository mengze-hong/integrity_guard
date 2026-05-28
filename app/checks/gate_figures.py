"""Gate 4: Figure & Table Cross-Reference Integrity.

Verifies:
1. Every \\begin{table}/\\begin{figure} has a \\label inside it
2. Every \\label{fig:x}/\\label{tab:x} is \\ref'd at least once in text
3. Every \\ref{fig:x}/\\ref{tab:x} points to an existing label
4. Produces a structured table showing each figure/table with:
   - Caption/title
   - Label
   - Where it's referenced (section/paragraph)
"""

import re
from pathlib import Path

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity, TexFile


# Patterns
_ENV_PATTERN = re.compile(
    r"\\begin\{(figure|table)\*?\}(.*?)\\end\{\1\*?\}",
    re.DOTALL,
)
_CAPTION_PATTERN = re.compile(r"\\caption(?:\[.*?\])?\{(.+?)\}", re.DOTALL)
_LABEL_IN_ENV = re.compile(r"\\label\{([^}]+)\}")
_SECTION_PATTERN = re.compile(r"\\(section|subsection)\*?\{([^}]+)\}")


def _find_ref_locations(tex_files: list[TexFile]) -> dict[str, list[dict]]:
    """Find where each \\ref{key} appears (which section, line context)."""
    ref_locations: dict[str, list[dict]] = {}

    for tex_file in tex_files:
        lines = tex_file.raw_text.split("\n")
        current_section = "Preamble"

        for line_num, line in enumerate(lines, 1):
            # Track current section
            sec_match = _SECTION_PATTERN.search(line)
            if sec_match:
                current_section = sec_match.group(2)

            # Find all \ref in this line
            for ref_match in re.finditer(r"\\(?:ref|cref|Cref|autoref)\{([^}]+)\}", line):
                key = ref_match.group(1)
                if key not in ref_locations:
                    ref_locations[key] = []
                ref_locations[key].append({
                    "file": tex_file.path.name,
                    "line": line_num,
                    "section": current_section,
                    "context": line.strip()[:80],
                })

    return ref_locations


def _extract_floats(tex_files: list[TexFile]) -> list[dict]:
    """Extract all figure/table environments with their captions and labels."""
    floats = []

    for tex_file in tex_files:
        # Find position of \appendix command (if any)
        appendix_pos = None
        appendix_match = re.search(r"\\appendix\b", tex_file.raw_text)
        if appendix_match:
            appendix_pos = appendix_match.start()

        for match in _ENV_PATTERN.finditer(tex_file.raw_text):
            env_type = match.group(1)  # "figure" or "table"
            env_content = match.group(2)

            # Extract caption
            caption_match = _CAPTION_PATTERN.search(env_content)
            caption = caption_match.group(1).strip() if caption_match else None
            # Clean caption (remove \label inside caption if any)
            if caption:
                caption = re.sub(r"\\label\{[^}]+\}", "", caption).strip()
                caption = re.sub(r"\s+", " ", caption)
                if len(caption) > 100:
                    caption = caption[:97] + "..."

            # Extract label
            label_match = _LABEL_IN_ENV.search(env_content)
            label = label_match.group(1) if label_match else None

            # Determine position in file
            start_pos = match.start()
            line_num = tex_file.raw_text[:start_pos].count("\n") + 1

            # Determine if this float is in the appendix
            in_appendix = appendix_pos is not None and start_pos > appendix_pos

            floats.append({
                "type": env_type,
                "caption": caption,
                "label": label,
                "file": tex_file.path.name,
                "line": line_num,
                "in_appendix": in_appendix,
            })

    return floats


class FigureTableGate(BaseGate):
    """Gate 4: Figure & Table cross-reference integrity check."""

    name = "figure_table_crossref"
    description = "图表交叉引用：验证所有图表有标签、标题，且在正文中被引用"
    is_blocking = True

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []

        # Extract all figure/table environments
        floats = _extract_floats(paper.tex_files)

        # Find all \ref locations
        ref_locations = _find_ref_locations(paper.tex_files)

        # Collect all float labels
        float_labels = {f["label"] for f in floats if f["label"]}

        # Build the cross-reference table
        crossref_table: list[dict] = []

        for i, flt in enumerate(floats):
            env_type = flt["type"].capitalize()
            num = sum(1 for f in floats[:i + 1] if f["type"] == flt["type"])
            display_name = f"{env_type} {num}"

            entry = {
                "display_name": display_name,
                "caption": flt["caption"] or "⚠️ NO CAPTION",
                "label": flt["label"] or "⚠️ MISSING",
                "type": flt["type"],
                "file": flt["file"],
                "line": flt["line"],
                "referenced_in": [],
                "has_label": flt["label"] is not None,
                "has_caption": flt["caption"] is not None,
                "is_referenced": False,
            }

            # Check if this float is referenced
            if flt["label"] and flt["label"] in ref_locations:
                entry["referenced_in"] = ref_locations[flt["label"]]
                entry["is_referenced"] = True

            crossref_table.append(entry)

            # Issue: no label
            if not flt["label"]:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"{display_name} 缺少 \\label — 无法被正文引用",
                    location=f"{flt['file']}:{flt['line']}",
                    evidence=f"Caption: {flt['caption'] or 'N/A'}",
                    suggestion=f"在 {flt['type']} 环境内添加 \\label{{{flt['type']}:meaningful_name}}。",
                    file=flt["file"],
                    line=flt["line"],
                ))

            # Issue: no caption
            if not flt["caption"]:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"{display_name} 缺少 \\caption",
                    location=f"{flt['file']}:{flt['line']}",
                    suggestion="每个图表必须有描述性的 caption。请添加 \\caption{{...}}。",
                    file=flt["file"],
                    line=flt["line"],
                ))

            # Issue: not referenced in text (skip for appendix floats)
            if flt["label"] and flt["label"] not in ref_locations and not flt.get("in_appendix"):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"{display_name} (\\label{{{flt['label']}}}) 在正文中从未被引用",
                    location=f"{flt['file']}:{flt['line']}",
                    evidence=f"Caption: {flt['caption'] or 'N/A'}",
                    suggestion=f"在正文合适位置添加 \\ref{{{flt['label']}}} 或 \\cref{{{flt['label']}}} 来引用此图表。",
                ))

        # Check for dangling \ref{fig:*} or \ref{tab:*} pointing to non-existent floats
        fig_tab_ref_keys = {
            k for k in ref_locations.keys()
            if k.startswith(("fig:", "tab:", "figure:", "table:"))
        }
        dangling_refs = fig_tab_ref_keys - float_labels
        for key in sorted(dangling_refs):
            locs = ref_locations[key]
            loc_str = ", ".join(f"{l['section']}" for l in locs[:3])
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"\\ref{{{key}}} points to non-existent figure/table",
                location=loc_str,
                evidence=f"Referenced in: {', '.join(l['file'] + ':' + str(l['line']) for l in locs[:3])}",
                suggestion=f"Either create a figure/table with \\label{{{key}}} or fix the \\ref.",
            ))

        # Compute score
        total_floats = len(floats)
        if total_floats == 0:
            score = 100.0
            passed = len(issues) == 0
        else:
            problems = sum(1 for f in crossref_table if not f["has_label"] or not f["is_referenced"] or not f["has_caption"])
            score = max(0, (1 - problems / total_floats) * 100)
            error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
            passed = error_count == 0

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=f"{total_floats} floats ({sum(1 for f in floats if f['type'] == 'figure')} figures, {sum(1 for f in floats if f['type'] == 'table')} tables)",
            metadata={"crossref_table": crossref_table},
        )
