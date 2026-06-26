"""BibTeX .bbl file parser.

arxiv source packages typically include a compiled .bbl file (the output of
BibTeX/biber) rather than the original .bib. This parser extracts bibliography
entries from .bbl files so gate_references can still verify them.

Two formats are handled:
  - Traditional BibTeX / natbib  (\bibitem[...]{key} + \newblock lines)
  - biblatex refsection format    (\\entry{key}{type}{...} + \\field / \\name)

The output BibEntry objects are compatible with those from bib_parser.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.models import BibEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\{([^}]*)\}")
_LATEX_CMD_NOARG = re.compile(r"\\[a-zA-Z]+\*?")
_BRACES = re.compile(r"[{}]")
_HREF = re.compile(r"\\href\s*\{([^}]+)\}\s*\{([^}]*)\}", re.IGNORECASE)
_URL_IN_TEXT = re.compile(r"https?://\S+", re.IGNORECASE)
_DOI_PATTERN = re.compile(r"10\.\d{4,9}/\S+")
_TILDE = re.compile(r"~")


def _strip_latex(s: str) -> str:
    """Remove LaTeX markup from a string, retaining plain text."""
    s = _HREF.sub(r"\2", s)  # \href{url}{text} → text
    s = _LATEX_CMD.sub(r"\1", s)  # \cmd{arg} → arg
    s = _LATEX_CMD_NOARG.sub(" ", s)  # \cmd → space
    s = _BRACES.sub("", s)
    s = _TILDE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _extract_doi(text: str) -> str | None:
    """Extract first DOI found in raw text (from \\href, doi= field, or bare URL)."""
    # \href{https://doi.org/10.xxx/yyy}{...}
    for url, _ in _HREF.findall(text):
        url = url.strip()
        m = _DOI_PATTERN.search(url)
        if m:
            return m.group(0)
    # bare doi.org URL
    for url in _URL_IN_TEXT.findall(text):
        if "doi.org" in url:
            m = _DOI_PATTERN.search(url)
            if m:
                return m.group(0)
    # raw 10.xxx/yyy pattern
    m = _DOI_PATTERN.search(text)
    if m:
        return m.group(0)
    return None


def _extract_url(text: str) -> str | None:
    """Extract a plausible source URL from raw text."""
    for url in _URL_IN_TEXT.findall(text):
        url = url.rstrip(".,;)")
        if any(pat in url for pat in [
            "arxiv.org", "aclanthology.org", "openreview.net",
            "proceedings.mlr.press", "proceedings.neurips.cc",
            "doi.org", "dl.acm.org", "ieeexplore.ieee.org",
            "link.springer.com", "semanticscholar.org",
        ]):
            return url
    # fallback: any https URL
    for url in _URL_IN_TEXT.findall(text):
        return url.rstrip(".,;)")
    return None


def _parse_authors_text(raw: str) -> list[str]:
    """Parse a plain-text author line like 'First Last, First2 Last2, and ...'"""
    raw = _strip_latex(raw)
    # Split on " and " then on commas (but not inside names)
    parts = re.split(r"\s+and\s+", raw, flags=re.IGNORECASE)
    authors = []
    for part in parts:
        # Sub-split on comma only if what follows looks like another name
        sub = [s.strip() for s in re.split(r",\s*(?=[A-Z])", part)]
        authors.extend(s for s in sub if len(s) > 1)
    return [a for a in authors if a]


# ---------------------------------------------------------------------------
# Traditional bibtex / natbib parser
# ---------------------------------------------------------------------------
# Format:
#   \bibitem[{Human label}]{cite-key}
#   Authors. Year.
#   \newblock Title.
#   \newblock In/Journal venue.
# ---------------------------------------------------------------------------

_BIBITEM_HEAD = re.compile(
    r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}(.*?)(?=\\bibitem|\Z)",
    re.DOTALL,
)

# natbib label like [{Vaswani et~al.(2017)Vaswani, ...}{key}] — key is second
_NATBIB_HEAD = re.compile(r"\\bibitem\s*\[\{[^}]*\}\{([^}]+)\}\]")


def _parse_traditional_bbl(text: str, source_file: str) -> list[BibEntry]:
    """Parse natbib / plain bibtex .bbl format."""
    entries: list[BibEntry] = []

    for m in _BIBITEM_HEAD.finditer(text):
        key = m.group(1).strip()
        body = m.group(2).strip()

        # Collect \newblock segments and the opening author line
        blocks = re.split(r"\\newblock\s*", body)

        # Block 0 is the author+year line (before first \newblock)
        # Remaining blocks are: title, venue, (optional extras)
        raw_author_line = _strip_latex(blocks[0]).strip() if blocks else ""

        # Extract year from author line: last 4-digit number
        year_m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", raw_author_line)
        year = year_m.group(1) if year_m else None

        # Title is usually block[1]
        title: str | None = None
        venue: str | None = None
        doi: str | None = None
        url: str | None = None

        for i, block in enumerate(blocks[1:], 1):
            doi = doi or _extract_doi(block)
            url = url or _extract_url(block)
            cleaned = _strip_latex(block).strip().rstrip(".")
            if not cleaned:
                continue
            # Year may appear at end of venue block: "..., pages 1–5, 2019."
            if year is None:
                ym = re.search(r"\b(1[89]\d{2}|20\d{2})\b", cleaned)
                if ym:
                    year = ym.group(1)
            if title is None:
                # Remove trailing year/comma artifacts for cleaner title
                title = re.sub(r",?\s*(1[89]\d{2}|20\d{2})\s*$", "", cleaned).strip()
            elif venue is None:
                # Typical venue prefixes
                if any(cleaned.startswith(p) for p in ("In ", "In\n", "Journal", "Proceedings", "arXiv")):
                    venue = cleaned
                elif re.match(r"[A-Z]", cleaned):
                    venue = cleaned

        # Parse authors: remove trailing year + period if present
        raw_author_line = re.sub(r",?\s*\b(1[89]\d{2}|20\d{2})\b\.?\s*$", "", raw_author_line).strip()
        authors = _parse_authors_text(raw_author_line) if raw_author_line else []

        # Split journal vs booktitle heuristic
        journal = None
        booktitle = None
        if venue:
            if venue.startswith("In "):
                booktitle = venue[3:].strip()
            else:
                journal = venue

        entries.append(BibEntry(
            key=key,
            entry_type="misc",
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            journal=journal,
            booktitle=booktitle,
            url=url,
            raw_fields={},
            source_file=source_file,
        ))

    return entries


# ---------------------------------------------------------------------------
# biblatex refsection parser
# ---------------------------------------------------------------------------
# Format:
#   \entry{cite-key}{type}{}
#     \name{author}{N}{}{{...}{family}{given}...}
#     \field{title}{...}
#     \field{year}{...}
#     \field{doi}{...}
#   \endentry
# ---------------------------------------------------------------------------

_BIBLATEX_ENTRY = re.compile(
    r"\\entry\s*\{([^}]+)\}\s*\{([^}]+)\}\s*\{[^}]*\}(.*?)\\endentry",
    re.DOTALL,
)
_BL_FIELD = re.compile(r"\\field\s*\{(\w+)\}\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}")
_BL_NAME_FAMILY = re.compile(r"\{family\}\{([^}]+)\}")
_BL_NAME_GIVEN = re.compile(r"\{given\}\{([^}]+)\}")


def _parse_biblatex_bbl(text: str, source_file: str) -> list[BibEntry]:
    """Parse biblatex .bbl format."""
    entries: list[BibEntry] = []

    for m in _BIBLATEX_ENTRY.finditer(text):
        key = m.group(1).strip()
        etype = m.group(2).strip()
        body = m.group(3)

        fields: dict[str, str] = {}
        for fm in _BL_FIELD.finditer(body):
            fname = fm.group(1).lower()
            fval = _strip_latex(fm.group(2))
            fields[fname] = fval

        # Parse authors from \name{author} block
        author_block_m = re.search(r"\\name\{author\}\{[^}]*\}\{(.*?)\}(?=\s*\\(?:name|field|endentry))", body, re.DOTALL)
        authors: list[str] = []
        if author_block_m:
            ab = author_block_m.group(1)
            families = _BL_NAME_FAMILY.findall(ab)
            givens = _BL_NAME_GIVEN.findall(ab)
            for fam, giv in zip(families, givens):
                fam = _strip_latex(fam)
                giv = _strip_latex(giv)
                if giv:
                    authors.append(f"{giv} {fam}")
                else:
                    authors.append(fam)
            if not authors:
                for fam in families:
                    authors.append(_strip_latex(fam))

        doi = fields.get("doi") or _extract_doi(body)
        url = fields.get("url") or _extract_url(body)

        journal = fields.get("journaltitle") or fields.get("journal")
        booktitle = fields.get("booktitle")

        entries.append(BibEntry(
            key=key,
            entry_type=etype,
            title=fields.get("title"),
            authors=authors,
            year=fields.get("year"),
            doi=doi,
            journal=journal,
            booktitle=booktitle,
            url=url,
            raw_fields=fields,
            source_file=source_file,
        ))

    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_bbl_file(file_path: Path) -> list[BibEntry]:
    """Parse a .bbl file and return BibEntry list.

    Automatically detects biblatex vs traditional bibtex format.
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    source = file_path.name

    # biblatex format has \entry{...}{...}{...} ... \endentry blocks
    if r"\entry{" in text or r"\endentry" in text:
        entries = _parse_biblatex_bbl(text, source)
    else:
        entries = _parse_traditional_bbl(text, source)

    # Filter out empty/sentinel entries
    return [e for e in entries if e.key and e.key not in ("", "noop")]


def parse_all_bbl_files(bbl_paths: list[Path]) -> list[BibEntry]:
    """Parse all .bbl files, deduplicate by citation key, and return merged list."""
    seen_keys: set[str] = set()
    all_entries: list[BibEntry] = []
    for path in bbl_paths:
        for entry in parse_bbl_file(path):
            if entry.key not in seen_keys:
                seen_keys.add(entry.key)
                all_entries.append(entry)
    return all_entries


def parse_inline_bibliography(tex_raw: str, source_label: str = "inline") -> list[BibEntry]:
    """Extract entries from an inline \\begin{thebibliography}...\\end{thebibliography} block.

    Some papers (especially single-file submissions) embed the bibliography
    directly in the .tex file instead of using a separate .bib or .bbl.
    This is functionally identical to the traditional .bbl format.
    """
    # Extract the thebibliography block
    m = re.search(
        r"\\begin\{thebibliography\}[^\n]*\n(.*?)\\end\{thebibliography\}",
        tex_raw,
        re.DOTALL,
    )
    if not m:
        return []

    # Reuse traditional bbl parser on the extracted block
    block = "\\begin{thebibliography}{}\n" + m.group(1) + "\\end{thebibliography}"
    entries = _parse_traditional_bbl(block, source_label)
    return [e for e in entries if e.key]


def extract_inline_bib_entries(tex_files) -> list[BibEntry]:
    """Scan a list of TexFile objects for inline thebibliography blocks."""
    seen_keys: set[str] = set()
    all_entries: list[BibEntry] = []
    for tex_file in tex_files:
        for entry in parse_inline_bibliography(tex_file.raw_text, tex_file.path.name):
            if entry.key not in seen_keys:
                seen_keys.add(entry.key)
                all_entries.append(entry)
    return all_entries
