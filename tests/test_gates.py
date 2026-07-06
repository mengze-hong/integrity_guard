"""Tests for gate checks."""

import struct
from pathlib import Path

import pytest

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


def _build_structure_paper(
    project_dir: Path,
    tex_file: TexFile,
    figure_files: list[Path] | None = None,
) -> ParsedPaper:
    """Build a minimal ParsedPaper for StructureGate tests."""
    bib_path = project_dir / "refs.bib"
    if not bib_path.exists():
        bib_path.write_text("@article{x,title={X}}", encoding="utf-8")

    return ParsedPaper(
        project_dir=project_dir,
        tex_files=[tex_file],
        bib_entries=[BibEntry(key="x", entry_type="article")],
        bib_file_path=bib_path,
        all_files=list(project_dir.rglob("*")),
        figure_files=figure_files or [],
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
@pytest.mark.parametrize("extension", [".png", ".pdf", ".jpg", ".jpeg", ".eps"])
async def test_structure_gate_resolves_extensionless_graphics_with_graphicspath(tmp_path, extension):
    """Structure gate resolves extensionless graphics through graphicspath."""
    figures = tmp_path / "figures"
    figures.mkdir()
    image_path = figures / f"plot{extension}"
    image_path.write_text(f"fake image {extension}", encoding="utf-8")
    (tmp_path / "refs.bib").write_text("@article{x,title={X}}", encoding="utf-8")
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}}
\addbibresource{refs.bib}
\begin{document}
\includegraphics{plot}
\end{document}
""",
        encoding="utf-8",
    )
    tex = parse_tex_file(tex_path)
    paper = _build_structure_paper(tmp_path, tex, figure_files=[image_path])

    result = await StructureGate().check(paper)
    messages = [issue.message for issue in result.issues]
    assert not any("图片文件不存在" in m for m in messages)
    assert not any("addbibresource" in m for m in messages)


@pytest.mark.asyncio
async def test_structure_gate_resolves_multiple_graphicspath_dirs(tmp_path):
    """Multiple graphicspath directories can satisfy different graphics."""
    figures = tmp_path / "figures"
    plots = tmp_path / "plots"
    figures.mkdir()
    plots.mkdir()
    plot_path = figures / "plot.png"
    chart_path = plots / "chart.pdf"
    plot_path.write_text("fake png", encoding="utf-8")
    chart_path.write_text("fake pdf", encoding="utf-8")
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}{plots/}}
\begin{document}
\includegraphics{plot}
\includegraphics{chart}
\end{document}
""",
        encoding="utf-8",
    )
    paper = _build_structure_paper(
        tmp_path,
        parse_tex_file(tex_path),
        figure_files=[plot_path, chart_path],
    )

    result = await StructureGate().check(paper)

    messages = [issue.message for issue in result.issues]
    assert not any("图片文件不存在" in m for m in messages)


@pytest.mark.asyncio
async def test_structure_gate_warns_when_graphicspath_has_no_supported_suffix(tmp_path):
    """Unsupported graphicspath image suffixes should still warn as missing."""
    figures = tmp_path / "figures"
    figures.mkdir()
    unsupported_path = figures / "plot.svg"
    unsupported_path.write_text("<svg></svg>", encoding="utf-8")
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}}
\begin{document}
\includegraphics{plot}
\end{document}
""",
        encoding="utf-8",
    )
    paper = _build_structure_paper(
        tmp_path,
        parse_tex_file(tex_path),
        figure_files=[unsupported_path],
    )

    result = await StructureGate().check(paper)

    warning_messages = [
        issue.message for issue in result.issues if issue.severity == Severity.WARNING
    ]
    assert any("图片文件不存在" in m and "plot" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_structure_gate_warns_low_resolution_and_large_images(tmp_path):
    """Structure gate surfaces basic image quality and optimization hints."""
    figures = tmp_path / "figures"
    figures.mkdir()
    low_png = figures / "tiny.png"
    low_png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", 320, 240)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    large_pdf = figures / "huge.pdf"
    with large_pdf.open("wb") as fh:
        fh.write(b"%PDF-1.4\n")
        fh.truncate(6 * 1024 * 1024)

    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}}
\begin{document}
\includegraphics{tiny.png}
\includegraphics{huge.pdf}
\end{document}
""",
        encoding="utf-8",
    )
    paper = _build_structure_paper(
        tmp_path,
        parse_tex_file(tex_path),
        figure_files=[low_png, large_pdf],
    )

    result = await StructureGate().check(paper)

    warning_messages = [
        issue.message for issue in result.issues if issue.severity == Severity.WARNING
    ]
    assert any("图片像素偏低" in m and "tiny.png" in m for m in warning_messages)
    assert any("图片文件过大" in m and "huge.pdf" in m for m in warning_messages)


@pytest.mark.asyncio
async def test_structure_gate_detects_duplicate_images(tmp_path):
    """Identical image content (same bytes) is flagged as duplicate, distinct content is not."""
    figures = tmp_path / "figures"
    figures.mkdir()
    payload = b"\x89PNG\r\n\x1a\n" + b"DUPLICATE-IMAGE-CONTENT" * 64
    (figures / "a.png").write_bytes(payload)
    (figures / "b.png").write_bytes(payload)  # same bytes -> duplicate
    (figures / "c.png").write_bytes(payload + b"different-tail")  # different content/size

    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}}
\begin{document}
\includegraphics{a.png}
\includegraphics{b.png}
\includegraphics{c.png}
\end{document}
""",
        encoding="utf-8",
    )
    paper = _build_structure_paper(
        tmp_path,
        parse_tex_file(tex_path),
        figure_files=[figures / "a.png", figures / "b.png", figures / "c.png"],
    )

    result = await StructureGate().check(paper)

    dup_messages = [i for i in result.issues if "重复图片文件" in i.message]
    assert len(dup_messages) == 1
    evidence = dup_messages[0].evidence
    assert "a.png" in evidence and "b.png" in evidence
    assert "c.png" not in evidence


@pytest.mark.asyncio
async def test_structure_gate_unique_sizes_skip_duplicate_warning(tmp_path):
    """Images with distinct byte sizes never trigger a duplicate warning."""
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "x.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"X" * 100)
    (figures / "y.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"Y" * 200)

    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\graphicspath{{figures/}}
\begin{document}
\includegraphics{x.png}
\includegraphics{y.png}
\end{document}
""",
        encoding="utf-8",
    )
    paper = _build_structure_paper(
        tmp_path,
        parse_tex_file(tex_path),
        figure_files=[figures / "x.png", figures / "y.png"],
    )

    result = await StructureGate().check(paper)
    assert not any("重复图片文件" in i.message for i in result.issues)


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


# ── NCG tests ────────────────────────────────────────────────────────────────

def _ncg_paper(tex_body: str) -> "ParsedPaper":
    """Helper: wrap raw tex body in a minimal ParsedPaper."""
    tex = TexFile(path=Path("test.tex"), is_main=True, raw_text=tex_body, citations=[])
    return ParsedPaper(project_dir=FIXTURES, tex_files=[tex], bib_entries=[], all_files=[], figure_files=[])


@pytest.mark.asyncio
async def test_ncg_tier0_detects_mismatch():
    """Tier 0 scope-first: claim 89.3 F1 for OurModel but table has 88.5."""
    tex = (
        r"\begin{table}" + "\n"
        r"\caption{Main results on SQuAD}" + "\n"
        r"\begin{tabular}{lcc}" + "\n"
        r"Model & F1 & Accuracy \\" + "\n"
        r"\hline" + "\n"
        r"OurModel & 88.5 & 91.2 \\" + "\n"
        r"Baseline & 85.1 & 88.0 \\" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}" + "\n\n"
        r"Our model achieves an F1 of 89.3 on SQuAD benchmark."
    )
    result = await DataIntegrityGate().check(_ncg_paper(tex))
    ncg_issues = [i for i in result.issues if "89.3" in i.message or "88.5" in i.message]
    assert ncg_issues, "NCG Tier 0 should detect F1 mismatch (89.3 claimed vs 88.5 in table)"


@pytest.mark.asyncio
async def test_ncg_no_fp_on_consistent_claim():
    """No false positive when claim matches table exactly at stated precision."""
    tex = (
        r"\begin{table}" + "\n"
        r"\caption{Results}" + "\n"
        r"\begin{tabular}{lc}" + "\n"
        r"Model & F1 \\" + "\n"
        r"\hline" + "\n"
        r"OurModel & 88.5 \\" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}" + "\n\n"
        r"Our model achieves an F1 of 88.5 on this task."
    )
    result = await DataIntegrityGate().check(_ncg_paper(tex))
    ncg_issues = [i for i in result.issues if "88.5" in i.message]
    assert not ncg_issues, f"Should not flag consistent claim: {[i.message for i in ncg_issues]}"


@pytest.mark.asyncio
async def test_ncg_no_fp_on_rounded_claim():
    """No false positive: 88.50 in text vs 88.504 in table — agrees at 2dp."""
    tex = (
        r"\begin{table}" + "\n"
        r"\caption{Results}" + "\n"
        r"\begin{tabular}{lc}" + "\n"
        r"Model & F1 \\" + "\n"
        r"\hline" + "\n"
        r"OurModel & 88.504 \\" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}" + "\n\n"
        r"Our model achieves an F1 of 88.50 on this task."
    )
    result = await DataIntegrityGate().check(_ncg_paper(tex))
    ncg_issues = [i for i in result.issues if "88.50" in i.message or "88.504" in i.message]
    assert not ncg_issues, f"Rounding should not trigger NCG: {[i.message for i in ncg_issues]}"


# ── Impossible value tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_impossible_value_f1_over_100():
    """F1 = 102.3 in a table column labelled F1 should be flagged as impossible."""
    tex = (
        r"\begin{table}" + "\n"
        r"\caption{Main results}" + "\n"
        r"\begin{tabular}{lcc}" + "\n"
        r"Model & F1 & Accuracy \\" + "\n"
        r"\hline" + "\n"
        r"OurModel & 102.3 & 91.2 \\" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}"
    )
    result = await DataIntegrityGate().check(_ncg_paper(tex))
    impossible = [i for i in result.issues if "102.3" in i.message or "超过 100" in i.message]
    assert impossible, "F1 > 100 should be flagged"
    assert any(i.severity.value == "error" for i in impossible)


@pytest.mark.asyncio
async def test_no_impossible_flag_on_valid_values():
    """Normal accuracy=91.2, F1=88.5 should not trigger impossible value check."""
    tex = (
        r"\begin{table}" + "\n"
        r"\caption{Results}" + "\n"
        r"\begin{tabular}{lcc}" + "\n"
        r"Model & F1 & Accuracy \\" + "\n"
        r"\hline" + "\n"
        r"OurModel & 88.5 & 91.2 \\" + "\n"
        r"\end{tabular}" + "\n"
        r"\end{table}"
    )
    result = await DataIntegrityGate().check(_ncg_paper(tex))
    impossible = [i for i in result.issues if "超过 100" in i.message or "不可能" in i.message]
    assert not impossible, f"Valid values should not trigger impossible check: {[i.message for i in impossible]}"


# ── Template remnant tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_template_remnant_detected():
    """'TODO:' and 'lorem ipsum' in text should be flagged as template remnants."""
    tex = TexFile(
        path=Path("test.tex"), is_main=True,
        raw_text=(
            r"\documentclass{article}\begin{document}"
            "\nTODO: add experiments here.\nLorem ipsum dolor sit amet.\n"
            r"\end{document}"
        ),
        citations=[],
    )
    from app.models import ParsedPaper
    paper = ParsedPaper(project_dir=FIXTURES, tex_files=[tex], bib_entries=[], all_files=[], figure_files=[])
    result = await __import__("app.checks.gate_writing", fromlist=["WritingQualityGate"]).WritingQualityGate().check(paper)
    remnant_issues = [i for i in result.issues if "模板残留" in i.message]
    assert remnant_issues, "Template remnants should be detected"


@pytest.mark.asyncio
async def test_no_template_remnant_on_clean_text():
    """Normal academic text should not trigger template remnant detection."""
    tex = TexFile(
        path=Path("test.tex"), is_main=True,
        raw_text=(
            r"\documentclass{article}\begin{document}"
            "\nWe propose a novel method for text classification. "
            "Our approach achieves state-of-the-art results.\n"
            r"\end{document}"
        ),
        citations=[],
    )
    from app.models import ParsedPaper
    paper = ParsedPaper(project_dir=FIXTURES, tex_files=[tex], bib_entries=[], all_files=[], figure_files=[])
    result = await __import__("app.checks.gate_writing", fromlist=["WritingQualityGate"]).WritingQualityGate().check(paper)
    remnant_issues = [i for i in result.issues if "模板残留" in i.message]
    assert not remnant_issues, f"Clean text should not trigger remnant check: {[i.message for i in remnant_issues]}"
