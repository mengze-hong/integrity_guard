r"""LaTeX format normalization tool.

Automatically fixes common formatting inconsistencies:
1. Unify citation commands (\cite vs \citep)
2. Unify cross-reference format (Table 1 → Table~1)
3. Unify abbreviations (Fig. vs Figure)
4. Remove trailing whitespace and fix double spaces
5. Normalize tilde usage for non-breaking spaces
"""

import re
from pathlib import Path


def normalize_format(text: str, rules: list[str] | None = None) -> tuple[str, list[str]]:
    """Apply formatting normalization rules to LaTeX text.

    Args:
        text: Raw LaTeX source text
        rules: List of rule IDs to apply. None = all rules.

    Returns:
        (normalized_text, list_of_changes_made)
    """
    changes = []
    all_rules = rules or ["citation_cmd", "tilde", "trailing_ws", "double_space", "blank_lines", "abbreviations", "percent_comment"]

    if "citation_cmd" in all_rules:
        # Conservative citation unification: only bare \cite -> \citep.
        # Textual citations such as \citet keep their different semantics.
        lines = text.split("\n")
        fixed = 0
        pattern = r"\\cite(?![A-Za-z])(\s*(?:\[[^\]]*\]\s*){0,2}\{)"
        for i, line in enumerate(lines):
            if line.strip().startswith("%"):
                continue
            new_line, count = re.subn(pattern, r"\\citep\1", line)
            if count:
                lines[i] = new_line
                fixed += count
        if fixed > 0:
            text = "\n".join(lines)
            changes.append(f"统一引用命令: \\cite → \\citep ({fixed} 处)")

    if "tilde" in all_rules:
        # Table 1 → Table~1, Figure 2 → Figure~2, Section 3 → Section~3
        for word in ("Table", "Figure", "Fig\\.", "Section", "Equation", "Eq\\.", "Chapter", "Algorithm"):
            pattern = rf"({word})\s+(\d)"
            replacement = r"\1~\2"
            new_text = re.sub(pattern, replacement, text)
            if new_text != text:
                count = len(re.findall(pattern, text))
                changes.append(f"统一非断行空格: {word} X → {word}~X ({count} 处)")
                text = new_text

    if "trailing_ws" in all_rules:
        # Remove trailing whitespace on each line
        lines = text.split("\n")
        fixed = 0
        for i, line in enumerate(lines):
            stripped = line.rstrip()
            if stripped != line:
                lines[i] = stripped
                fixed += 1
        if fixed > 0:
            text = "\n".join(lines)
            changes.append(f"去除行尾空格 ({fixed} 行)")

    if "double_space" in all_rules:
        # Fix double spaces (but not in comments or after period)
        lines = text.split("\n")
        fixed = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("%"):
                continue
            # Replace double+ spaces with single (except after . which is LaTeX sentence spacing)
            new_line = re.sub(r"(?<![.!?])  +", " ", line)
            if new_line != line:
                lines[i] = new_line
                fixed += 1
        if fixed > 0:
            text = "\n".join(lines)
            changes.append(f"修复多余空格 ({fixed} 行)")

    if "blank_lines" in all_rules:
        # Keep paragraph breaks, but collapse noisy vertical whitespace.
        new_text = re.sub(r"\n{3,}", "\n\n", text)
        if new_text != text:
            count = len(re.findall(r"\n{3,}", text))
            changes.append(f"压缩多余空行 ({count} 处)")
            text = new_text

    if "abbreviations" in all_rules:
        # Unify Fig. / Figure references
        # "Fig. " at start of sentence should stay, but mid-sentence "Fig." is fine
        # Just ensure consistency: Fig.~\ref not Fig. \ref
        pattern = r"Fig\.\s+\\ref"
        replacement = r"Fig.~\\ref"
        new_text = re.sub(pattern, replacement, text)
        if new_text != text:
            count = len(re.findall(pattern, text))
            changes.append(f"统一 Fig.~\\ref 格式 ({count} 处)")
            text = new_text

        # Eq. \ref → Eq.~\ref
        pattern = r"Eq\.\s+\\ref"
        replacement = r"Eq.~\\ref"
        new_text = re.sub(pattern, replacement, text)
        if new_text != text:
            count = len(re.findall(pattern, text))
            changes.append(f"统一 Eq.~\\ref 格式 ({count} 处)")
            text = new_text

    if "percent_comment" in all_rules:
        # Ensure % comments have a space after % for readability
        # But don't touch \\% (escaped percent) or URLs
        lines = text.split("\n")
        fixed = 0
        for i, line in enumerate(lines):
            # Match lines where % is a comment (not escaped) and has no space after
            m = re.match(r"^(.*[^\\])%([^\s%].*)", line)
            if m and not m.group(1).strip().startswith("\\url"):
                lines[i] = m.group(1) + "% " + m.group(2)
                fixed += 1
        if fixed > 0:
            text = "\n".join(lines)
            changes.append(f"注释格式化: %后添加空格 ({fixed} 处)")

    return text, changes


def normalize_file(file_path: Path, rules: list[str] | None = None) -> list[str]:
    """Normalize a single .tex file in-place. Returns list of changes."""
    content = file_path.read_text(encoding="utf-8")
    normalized, changes = normalize_format(content, rules)
    if changes:
        file_path.write_text(normalized, encoding="utf-8")
    return changes
