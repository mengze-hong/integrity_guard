"""Tests for gate checks."""

import pytest
from pathlib import Path

from app.models import ParsedPaper, BibEntry, TexFile, Severity
from app.parsers.tex_parser import parse_tex_file
from app.parsers.bib_parser import parse_bib_file
from app.checks.gate_structure import StructureGate
from app.checks.gate_citations import CitationConsistencyGate
from app.checks.gate_writing import WritingQualityGate
from app.checks.gate_data import DataIntegrityGate


FIXTURES = Path(__file__).parent / "fixtures"


def _build_test_paper() -> ParsedPaper:
    """Build a ParsedPaper from test fixtures."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    bib_entries = parse_bib_file(FIXTURES / "sample_fake.bib")
    return ParsedPaper(
        project_dir=FIXTURES,
        tex_files=[tex],
        bib_entries=bib_entries,
        bib_file_path=FIXTURES / "sample_fake.bib",
        all_files=list(FIXTURES.glob("*")),
        figure_files=[],
    )


@pytest.mark.asyncio
async def test_citation_consistency_detects_undefined():
    """Test that Gate 3 catches undefined citation keys."""
    paper = _build_test_paper()
    gate = CitationConsistencyGate()
    result = await gate.check(paper)

    # Should detect 'nonexistent_key' as undefined
    error_messages = [i.message for i in result.issues if i.severity == Severity.ERROR]
    assert any("nonexistent_key" in m for m in error_messages)


@pytest.mark.asyncio
async def test_citation_consistency_detects_orphans():
    """Test that Gate 3 catches orphan .bib entries (not cited)."""
    # Create a paper with extra bib entries not cited
    paper = _build_test_paper()
    paper.bib_entries.append(
        BibEntry(key="uncited_paper", entry_type="article", title="Uncited Paper")
    )
    gate = CitationConsistencyGate()
    result = await gate.check(paper)

    warning_messages = [i.message for i in result.issues if i.severity == Severity.WARNING]
    assert any("uncited_paper" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_structure_gate_requires_tex():
    """Test that Gate 1 fails when no .tex files present."""
    paper = ParsedPaper(
        project_dir=FIXTURES,
        tex_files=[],
        bib_entries=[],
        all_files=[],
        figure_files=[],
    )
    gate = StructureGate()
    result = await gate.check(paper)
    assert result.passed is False
    assert result.score == 0.0


@pytest.mark.asyncio
async def test_structure_gate_warns_missing_graphics():
    """Test that Gate 1 warns about missing image files."""
    paper = _build_test_paper()
    gate = StructureGate()
    result = await gate.check(paper)

    # Should warn about missing figures/architecture.png
    messages = [i.message for i in result.issues]
    assert any("architecture" in m for m in messages)


@pytest.mark.asyncio
async def test_structure_gate_supports_graphicspath_and_addbibresource(tmp_path):
    """Structure gate should understand common graphicspath and biblatex syntax."""
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "plot.pdf").write_text("fake pdf", encoding="utf-8")
    (tmp_path / "refs.bib").write_text("@article{x,title={X}}", encoding="utf-8")
    tex_path = tmp_path / "main.tex"
    tex = TexFile(
        path=tex_path,
        is_main=True,
        raw_text=r"""
\documentclass{article}
\graphicspath{{figures/}}
\addbibresource{refs.bib}
\begin{document}
\includegraphics{plot}
\end{document}
""",
        citations=[],
        graphics=["plot"],
    )
    paper = ParsedPaper(
        project_dir=tmp_path,
        tex_files=[tex],
        bib_entries=[BibEntry(key="x", entry_type="article")],
        bib_file_path=tmp_path / "refs.bib",
        all_files=list(tmp_path.rglob("*")),
        figure_files=[figures / "plot.pdf"],
    )

    result = await StructureGate().check(paper)
    messages = [issue.message for issue in result.issues]
    assert not any("图片文件不存在" in m for m in messages)
    assert not any("addbibresource" in m for m in messages)


@pytest.mark.asyncio
async def test_writing_quality_detects_ai_markers():
    """Test that Gate 6 detects AI-generated text markers."""
    tex = TexFile(
        path=Path("test.tex"),
        is_main=True,
        raw_text="\\documentclass{article}\n\\begin{document}\nAs an AI language model, I cannot help you.\n\\end{document}",
        citations=[],
    )
    paper = ParsedPaper(
        project_dir=FIXTURES,
        tex_files=[tex],
        bib_entries=[],
        all_files=[],
        figure_files=[],
    )
    gate = WritingQualityGate()
    result = await gate.check(paper)

    error_messages = [i.message for i in result.issues if i.severity == Severity.ERROR]
    assert any("prompt" in m.lower() or "ai" in m.lower() for m in error_messages)


@pytest.mark.asyncio
async def test_writing_quality_ignores_comments_and_bibliography():
    """AI markers in comments/bibliography should not trigger writing errors."""
    tex = TexFile(
        path=Path("test.tex"),
        is_main=True,
        raw_text=(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "% As an AI language model, I cannot help you.\n"
            "This is normal prose.\n"
            "\\begin{thebibliography}{1}\n"
            "\\bibitem{x} As an AI language model, I cannot help you.\n"
            "\\end{thebibliography}\n"
            "\\end{document}"
        ),
        citations=[],
    )
    paper = ParsedPaper(project_dir=FIXTURES, tex_files=[tex], bib_entries=[], all_files=[], figure_files=[])

    result = await WritingQualityGate().check(paper)

    error_messages = [i.message for i in result.issues if i.severity == Severity.ERROR]
    assert not any("prompt" in m.lower() or "ai" in m.lower() for m in error_messages)


@pytest.mark.asyncio
async def test_writing_quality_detects_final_mode():
    """Test that Gate 6 detects [final] mode in ACL template."""
    tex = TexFile(
        path=Path("test.tex"),
        is_main=True,
        raw_text="\\usepackage[final]{acl}\n\\begin{document}\nHello world.\n\\end{document}",
        citations=[],
    )
    paper = ParsedPaper(
        project_dir=FIXTURES,
        tex_files=[tex],
        bib_entries=[],
        all_files=[],
        figure_files=[],
    )
    gate = WritingQualityGate()
    result = await gate.check(paper)

    messages = [i.message for i in result.issues]
    assert any("[final]" in m for m in messages)


@pytest.mark.asyncio
async def test_data_integrity_detects_duplicate_rows():
    """Test that Gate 5 detects duplicate table rows."""
    tex = TexFile(
        path=Path("test.tex"),
        is_main=True,
        raw_text=open(FIXTURES / "sample_table.tex").read(),
        citations=[],
    )
    paper = ParsedPaper(
        project_dir=FIXTURES,
        tex_files=[tex],
        bib_entries=[],
        all_files=[],
        figure_files=[],
    )
    gate = DataIntegrityGate()
    result = await gate.check(paper)

    # sample_table.tex has duplicate rows (Baseline == Ours (dup))
    error_messages = [i.message for i in result.issues if i.severity == Severity.ERROR]
    assert any("相同" in m for m in error_messages)
