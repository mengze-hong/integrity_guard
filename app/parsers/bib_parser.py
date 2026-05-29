"""BibTeX parser - extract bibliography entries from .bib files."""

import re
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode

from app.models import BibEntry


def _parse_authors(author_str: str) -> list[str]:
    """Parse author string into list of individual author names.

    Handles both "Last, First and Last, First" and "First Last and First Last" formats.
    """
    if not author_str:
        return []
    # Split on " and " (BibTeX standard separator)
    authors = re.split(r"\s+and\s+", author_str)
    # Clean up each author name
    return [a.strip() for a in authors if a.strip()]


def _normalize_doi(doi: str | None) -> str | None:
    """Normalize common DOI forms from BibTeX fields."""
    if not doi:
        return None
    cleaned = doi.strip().strip("{}\"'")
    cleaned = re.sub(r"\\_", "_", cleaned)
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^doi:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip(".,;")
    return cleaned or None


def parse_bib_file(file_path: Path) -> list[BibEntry]:
    """Parse a .bib file and return structured entries."""
    text = file_path.read_text(encoding="utf-8", errors="replace")

    # Build a map from entry key → line number (scan for @type{key, patterns)
    key_line_map: dict[str, int] = {}
    for i, line in enumerate(text.split("\n"), 1):
        m = re.match(r"\s*@\w+\s*\{\s*([^,\s]+)", line)
        if m:
            key_line_map[m.group(1).strip()] = i

    parser = BibTexParser(common_strings=True)
    parser.customization = convert_to_unicode
    bib_db = bibtexparser.loads(text, parser=parser)

    entries = []
    for entry in bib_db.entries:
        key = entry.get("ID", "")
        bib_entry = BibEntry(
            key=key,
            entry_type=entry.get("ENTRYTYPE", "misc"),
            title=entry.get("title"),
            authors=_parse_authors(entry.get("author", "")),
            year=entry.get("year"),
            doi=_normalize_doi(entry.get("doi")),
            journal=entry.get("journal"),
            booktitle=entry.get("booktitle"),
            volume=entry.get("volume"),
            pages=entry.get("pages"),
            publisher=entry.get("publisher"),
            url=entry.get("url"),
            raw_fields={k: v for k, v in entry.items() if k not in ("ID", "ENTRYTYPE")},
            source_file=file_path.name,
            source_line=key_line_map.get(key),
        )
        entries.append(bib_entry)

    return entries


def parse_all_bib_files(bib_paths: list[Path]) -> list[BibEntry]:
    """Parse all .bib files and merge entries."""
    all_entries = []
    for path in bib_paths:
        all_entries.extend(parse_bib_file(path))
    return all_entries
