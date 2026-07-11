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


def _strip_comments(text: str) -> str:
    """Remove LaTeX comment lines/fragments while preserving line count.

    Lines whose first non-space character is % are blanked entirely.
    Inline comments (unescaped %) are stripped from the end of the line.
    Line count is preserved so that line-number reporting stays accurate.
    """
    out_lines = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("%"):
            out_lines.append("")
        else:
            # strip inline comment
            result = []
            i = 0
            while i < len(line):
                if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                    break
                result.append(line[i])
                i += 1
            out_lines.append("".join(result))
    return "\n".join(out_lines)


def _find_ref_locations(tex_files: list[TexFile]) -> dict[str, list[dict]]:
    """Find where each \\ref{key} appears (which section, line context).

    Comments are stripped first so refs inside % blocks are ignored.
    """
    ref_locations: dict[str, list[dict]] = {}

    for tex_file in tex_files:
        lines = tex_file.stripped_text.splitlines()
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
    """Extract all figure/table environments with their captions and labels.

    Comments are stripped first so commented-out environments are ignored.
    """
    floats = []

    for tex_file in tex_files:
        # Strip comments to avoid matching commented-out environments
        clean_text = tex_file.stripped_text

        # Find position of \appendix command (if any)
        appendix_pos = None
        appendix_match = re.search(r"\\appendix\b", clean_text)
        if appendix_match:
            appendix_pos = appendix_match.start()

        for match in _ENV_PATTERN.finditer(clean_text):
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

            # Determine position in file (line numbers preserved by _strip_comments)
            start_pos = match.start()
            line_num = clean_text[:start_pos].count("\n") + 1

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
    description = "Figure/table cross-references: verifies all floats have labels, captions, and are cited in text"
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
                "caption": flt["caption"] or "NO CAPTION",
                "label": flt["label"] or "MISSING",
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
                    message=f"{display_name} is missing \\label — cannot be referenced in text",
                    location=f"{flt['file']}:{flt['line']}",
                    evidence=f"Caption: {flt['caption'] or 'N/A'}",
                    suggestion=f"Add \\label{{{flt['type']}:meaningful_name}} inside the {flt['type']} environment.",
                    file=flt["file"],
                    line=flt["line"],
                ))

            # Issue: no caption
            if not flt["caption"]:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"{display_name} is missing \\caption",
                    location=f"{flt['file']}:{flt['line']}",
                    suggestion="Every float must have a descriptive caption. Add \\caption{{...}}.",
                    file=flt["file"],
                    line=flt["line"],
                ))

            # Issue: not referenced in text (skip for appendix floats)
            if flt["label"] and flt["label"] not in ref_locations and not flt.get("in_appendix"):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"{display_name} (\\label{{{flt['label']}}}) is never referenced in the text",
                    location=f"{flt['file']}:{flt['line']}",
                    evidence=f"Caption: {flt['caption'] or 'N/A'}",
                    suggestion=f"Add \\ref{{{flt['label']}}} or \\cref{{{flt['label']}}} at an appropriate location in the text to reference this float.",
                ))

        # Check for dangling \ref{fig:*} or \ref{tab:*} pointing to non-existent labels
        fig_tab_ref_keys = {
            k for k in ref_locations.keys()
            if k.startswith(("fig:", "tab:", "figure:", "table:"))
        }
        dangling_refs = fig_tab_ref_keys - float_labels
        for key in sorted(dangling_refs):
            locs = ref_locations[key]
            loc_str = ", ".join(f"{loc['section']}" for loc in locs[:3])
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"\\ref{{{key}}} references a non-existent float label",
                location=loc_str,
                evidence=f"Referenced at: {', '.join(loc['file'] + ':' + str(loc['line']) for loc in locs[:3])}",
                suggestion=f"Create a float with \\label{{{key}}}, or correct the label name in the \\ref.",
            ))

        # Compute score: 5 pts per error, 2 pts per warning
        total_floats = len(floats)
        if total_floats == 0:
            score = 100.0
            passed = len(issues) == 0
        else:
            error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
            warn_count = sum(1 for i in issues if i.severity == Severity.WARNING)
            score = max(0, 100 - error_count * 5 - warn_count * 2)
            passed = error_count == 0

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=(
                f"{total_floats} floats "
                f"({sum(1 for f in floats if f['type'] == 'figure')} figures, "
                f"{sum(1 for f in floats if f['type'] == 'table')} tables)"
            ),
            metadata={"crossref_table": crossref_table},
        )
