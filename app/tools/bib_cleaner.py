"""BibTeX cleaning utilities.

Features:
1. Indentation normalization (consistent 2-space indent)
2. Remove unnecessary fields (abstract, keywords, file, annote, note)
3. Lowercase field names
4. Sort entries by citation order in .tex files
5. Separate unused entries into unused.bib
"""

import re

from app.models import TexFile


# Fields to remove during cleaning
_REMOVE_FIELDS = {
    "abstract", "keywords", "file", "annote", "note",
    "mendeley-groups", "mendeley-tags", "bdsk-url-1", "bdsk-url-2",
    "date-added", "date-modified", "local-url", "uri", "rating",
}


def clean_bib_text(bib_text: str) -> str:
    """Clean a raw .bib file text: normalize indent, remove junk fields, lowercase."""
    entries = _parse_raw_entries(bib_text)
    cleaned = []
    for entry in entries:
        cleaned.append(_clean_single_entry(entry))
    return "\n\n".join(cleaned) + "\n"


def sort_bib_by_citation_order(bib_text: str, tex_files: list[TexFile]) -> str:
    """Sort .bib entries to match the order citations appear in .tex files."""
    # Get citation order from all tex files
    cite_order = []
    seen = set()
    for tex_file in tex_files:
        for key in tex_file.citations:
            if key not in seen:
                cite_order.append(key)
                seen.add(key)

    entries = _parse_raw_entries(bib_text)
    entry_map = {}  # key → raw entry text
    for entry in entries:
        key_match = re.match(r"@\w+\s*\{\s*([^,\s]+)", entry)
        if key_match:
            entry_map[key_match.group(1).strip()] = entry

    # Build sorted output
    sorted_entries = []
    remaining_keys = set(entry_map.keys())

    # First: entries in citation order
    for key in cite_order:
        if key in entry_map:
            sorted_entries.append(_clean_single_entry(entry_map[key]))
            remaining_keys.discard(key)

    # Then: remaining entries (not cited)
    for key in sorted(remaining_keys):
        sorted_entries.append(_clean_single_entry(entry_map[key]))

    return "\n\n".join(sorted_entries) + "\n"


def separate_unused(bib_text: str, tex_files: list[TexFile]) -> tuple[str, str]:
    """Split bib into used.bib and unused.bib based on citations in tex files.

    Returns: (used_bib_text, unused_bib_text)
    """
    # Collect all cited keys
    cited_keys = set()
    for tex_file in tex_files:
        cited_keys.update(tex_file.citations)

    entries = _parse_raw_entries(bib_text)
    used = []
    unused = []

    for entry in entries:
        key_match = re.match(r"@\w+\s*\{\s*([^,\s]+)", entry)
        if key_match:
            key = key_match.group(1).strip()
            if key in cited_keys:
                used.append(_clean_single_entry(entry))
            else:
                unused.append(_clean_single_entry(entry))
        else:
            used.append(entry)  # Keep non-entry lines (comments, strings)

    used_text = "\n\n".join(used) + "\n" if used else ""
    unused_text = "\n\n".join(unused) + "\n" if unused else ""
    return used_text, unused_text


def deduplicate_entries(bib_text: str) -> tuple[str, int]:
    """Remove duplicate bib entries (same key or same title).

    Returns: (deduped_text, num_removed)
    """
    entries = _parse_raw_entries(bib_text)
    seen_keys = set()
    seen_titles = set()
    unique = []
    removed = 0

    for entry in entries:
        key_match = re.match(r"@\w+\s*\{\s*([^,\s]+)", entry)
        if not key_match:
            unique.append(entry)
            continue

        key = key_match.group(1).strip()

        # Check duplicate key
        if key in seen_keys:
            removed += 1
            continue
        seen_keys.add(key)

        # Check duplicate title (normalized)
        title_match = re.search(r"title\s*=\s*\{(.+?)\}", entry, re.IGNORECASE | re.DOTALL)
        if title_match:
            title_norm = re.sub(r"\s+", " ", title_match.group(1).lower().strip())
            title_norm = re.sub(r"[{}\\]", "", title_norm)
            if title_norm in seen_titles and len(title_norm) > 20:
                removed += 1
                continue
            seen_titles.add(title_norm)

        unique.append(entry)

    return "\n\n".join(unique) + "\n", removed


def _parse_raw_entries(bib_text: str) -> list[str]:
    """Split raw bib text into individual entry strings."""
    entries = []
    current = []
    brace_depth = 0

    for line in bib_text.split("\n"):
        if re.match(r"\s*@\w+\s*\{", line) and brace_depth == 0:
            if current:
                entries.append("\n".join(current))
            current = [line]
            brace_depth = line.count("{") - line.count("}")
        elif current:
            current.append(line)
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                entries.append("\n".join(current))
                current = []
                brace_depth = 0

    if current:
        entries.append("\n".join(current))

    return entries


def _clean_single_entry(entry_text: str) -> str:
    """Clean a single bib entry: indent, remove fields, lowercase."""
    lines = entry_text.strip().split("\n")
    if not lines:
        return entry_text

    # Parse the entry type and key from first line
    first_line = lines[0].strip()
    type_match = re.match(r"@(\w+)\s*\{\s*([^,\s]+)\s*,?\s*$", first_line)
    if not type_match:
        return entry_text  # Can't parse, return as-is

    entry_type = type_match.group(1).lower()
    key = type_match.group(2)

    # Extract fields
    fields = []
    for line in lines[1:]:
        line = line.strip()
        if line == "}" or line == "},":
            continue
        # Match field = {value} or field = "value" or field = number
        field_match = re.match(r"(\w+)\s*=\s*(.+)", line)
        if field_match:
            field_name = field_match.group(1).lower()
            field_value = field_match.group(2).rstrip(",").strip()
            # Skip unwanted fields
            if field_name in _REMOVE_FIELDS:
                continue
            fields.append((field_name, field_value))

    # Rebuild entry with clean formatting
    result = [f"@{entry_type}{{{key},"]
    for name, value in fields:
        result.append(f"  {name} = {value},")
    result.append("}")

    return "\n".join(result)
