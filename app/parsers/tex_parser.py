"""TeX file parser - extract citations, labels, refs, sections from .tex files."""

import re
from pathlib import Path

from app.models import TexFile


# Regex patterns for LaTeX commands
_CITE_PATTERN = re.compile(r"\\cite[tp]?\*?\{([^}]+)\}")  # \cite, \citep, \citet
_LABEL_PATTERN = re.compile(r"\\label\{([^}]+)\}")
_REF_PATTERN = re.compile(r"\\(?:ref|eqref|cref|Cref|autoref)\{([^}]+)\}")
_INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")
_INCLUDE_PATTERN = re.compile(r"\\include\{([^}]+)\}")
_GRAPHICS_PATTERN = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
_SECTION_PATTERN = re.compile(
    r"\\(?:section|subsection|subsubsection)\*?\{([^}]+)\}"
)
_DOCUMENTCLASS_PATTERN = re.compile(r"\\documentclass")
_BEGIN_DOC_PATTERN = re.compile(r"\\begin\{document\}")


def parse_tex_file(file_path: Path) -> TexFile:
    """Parse a single .tex file and extract all relevant information."""
    raw_text = file_path.read_text(encoding="utf-8", errors="replace")

    # Strip LaTeX comments: remove everything after % (unless escaped \%)
    # Keep the raw_text intact for editor display, but use stripped version for analysis
    lines = raw_text.split("\n")
    stripped_lines = []
    for line in lines:
        # Find first unescaped % and remove everything after it
        result = ""
        i = 0
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i-1] != "\\"):
                break  # rest is comment
            result += line[i]
            i += 1
        stripped_lines.append(result)
    text = "\n".join(stripped_lines)

    # Extract citation keys (split comma-separated keys)
    citations = []
    for match in _CITE_PATTERN.finditer(text):
        keys = [k.strip() for k in match.group(1).split(",")]
        citations.extend(keys)

    # Extract labels
    labels = [m.group(1) for m in _LABEL_PATTERN.finditer(text)]

    # Extract refs
    refs = [m.group(1) for m in _REF_PATTERN.finditer(text)]

    # Extract inputs/includes
    inputs = [m.group(1) for m in _INPUT_PATTERN.finditer(text)]
    includes = [m.group(1) for m in _INCLUDE_PATTERN.finditer(text)]

    # Extract graphics paths
    graphics = [m.group(1) for m in _GRAPHICS_PATTERN.finditer(text)]

    # Extract section titles
    sections = [m.group(1) for m in _SECTION_PATTERN.finditer(text)]

    # Determine if this is the main file
    is_main = bool(_DOCUMENTCLASS_PATTERN.search(text) and _BEGIN_DOC_PATTERN.search(text))

    return TexFile(
        path=file_path,
        is_main=is_main,
        citations=list(dict.fromkeys(citations)),  # dedupe preserving order
        labels=labels,
        refs=refs,
        inputs=inputs,
        includes=includes,
        graphics=graphics,
        sections=sections,
        raw_text=raw_text,  # keep original (with comments) for editor display
    )


def parse_all_tex_files(tex_paths: list[Path]) -> list[TexFile]:
    """Parse all .tex files in the project."""
    return [parse_tex_file(p) for p in tex_paths]
