"""Core data models for the ScholarLint quality gate system."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


# --- Paper Structure Models ---


class BibEntry(BaseModel):
    """A single bibliography entry parsed from .bib file."""

    key: str  # citation key, e.g. "smith2024deep"
    entry_type: str  # article, inproceedings, book, etc.
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: str | None = None
    doi: str | None = None
    journal: str | None = None
    booktitle: str | None = None  # for conference papers
    volume: str | None = None
    pages: str | None = None
    publisher: str | None = None
    url: str | None = None
    raw_fields: dict[str, str] = Field(default_factory=dict)
    source_file: str | None = None  # which .bib file this came from
    source_line: int | None = None  # line number in .bib file


class TexFile(BaseModel):
    """Parsed information from a .tex file."""

    path: Path
    is_main: bool = False
    citations: list[str] = Field(default_factory=list)  # \cite{key} keys
    labels: list[str] = Field(default_factory=list)  # \label{xxx}
    refs: list[str] = Field(default_factory=list)  # \ref{xxx}
    inputs: list[str] = Field(default_factory=list)  # \input{file}
    includes: list[str] = Field(default_factory=list)  # \include{file}
    graphics: list[str] = Field(default_factory=list)  # \includegraphics paths
    sections: list[str] = Field(default_factory=list)  # section titles
    raw_text: str = ""
    stripped_text: str = ""  # raw_text with LaTeX comments removed (for analysis)

    @model_validator(mode="after")
    def _auto_strip(self) -> "TexFile":
        """If stripped_text not set, derive it from raw_text by removing % comments."""
        if not self.stripped_text and self.raw_text:
            lines = []
            for line in self.raw_text.splitlines():
                s = line.lstrip()
                if s.startswith("%"):
                    lines.append("")
                else:
                    out, i = [], 0
                    while i < len(line):
                        if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                            break
                        out.append(line[i])
                        i += 1
                    lines.append("".join(out))
            self.stripped_text = "\n".join(lines)
        return self


class ParsedPaper(BaseModel):
    """Complete parsed representation of an uploaded paper project."""

    project_dir: Path
    tex_files: list[TexFile] = Field(default_factory=list)
    bib_entries: list[BibEntry] = Field(default_factory=list)
    bib_file_path: Path | None = None
    all_files: list[Path] = Field(default_factory=list)
    figure_files: list[Path] = Field(default_factory=list)
    # BYOK: per-request LLM credentials ({api_key, base_url, model}) threaded
    # from the upload request so gates (NCG) use the user's own key. None =>
    # fall back to server settings (regex-only if server has no key).
    llm_config: dict | None = None


# --- Check Result Models ---


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Issue(BaseModel):
    """A single issue found during a check."""

    severity: Severity
    message: str
    location: str | None = None  # e.g. "refs.bib:entry_key" or "main.tex:42"
    evidence: str | None = None  # supporting evidence
    suggestion: str | None = None  # how to fix
    file: str | None = None  # which file this issue is in
    line: int | None = None  # line number in that file (1-indexed)


class CheckResult(BaseModel):
    """Result of a single gate check."""

    gate_name: str
    gate_description: str
    passed: bool
    score: float = Field(ge=0, le=100)  # 0-100 confidence
    issues: list[Issue] = Field(default_factory=list)
    summary: str = ""  # one-line summary
    metadata: dict = Field(default_factory=dict)  # gate-specific data (tables, links, etc.)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)


class DismissedIssue(BaseModel):
    """An issue that the student chose to dismiss with a reason."""

    gate_name: str
    issue_index: int
    reason: str
    original_message: str
    severity: Severity
    timestamp: str = ""


class FullReport(BaseModel):
    """Complete integrity check report."""

    job_id: str
    filename: str
    gate_results: list[CheckResult] = Field(default_factory=list)
    dismissed_issues: list[DismissedIssue] = Field(default_factory=list)
    overall_passed: bool = False
    overall_score: float = 0.0
    timestamp: str = ""
    project_dir: str = ""  # path to extracted files (for editor)
    metadata: dict = Field(default_factory=dict)  # paper stats (word count, etc.)

    def compute_overall(self) -> None:
        """Compute overall pass/fail from individual gates."""
        if not self.gate_results:
            self.overall_passed = False
            self.overall_score = 0.0
            return
        self.overall_passed = all(r.passed for r in self.gate_results)
        self.overall_score = sum(r.score for r in self.gate_results) / len(self.gate_results)
