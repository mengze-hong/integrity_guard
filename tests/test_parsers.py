"""Tests for parsers module."""

import zipfile

import pytest

from pathlib import Path

from app.parsers.tex_parser import parse_tex_file
from app.parsers.bib_parser import parse_bib_file
from app.parsers.zip_parser import extract_zip


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_tex_citations():
    """Test that tex parser correctly extracts citation keys."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert tex.is_main is True
    assert "real_entry_attention" in tex.citations
    assert "real_entry_bert" in tex.citations
    assert "fake_entry_1" in tex.citations
    assert "fake_entry_2" in tex.citations
    assert "nonexistent_key" in tex.citations


def test_parse_tex_extended_citation_commands(tmp_path):
    """Natbib/biblatex citation commands with optional args should be parsed."""
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\begin{document}
\citep[see][p. 3]{smith2020,doe2021}
\textcite{miller2022}
\autocite{nguyen2023}
\smartcite{smart2024}
\supercite{super2025}
\citeyearpar{year2026}
\citeposs{possessive2027}
\nocite{dataset2024}
\end{document}
""",
        encoding="utf-8",
    )

    tex = parse_tex_file(tex_path)
    assert tex.citations == [
        "smith2020",
        "doe2021",
        "miller2022",
        "nguyen2023",
        "smart2024",
        "super2025",
        "year2026",
        "possessive2027",
        "dataset2024",
    ]


def test_parse_tex_labels_and_refs():
    """Test label and ref extraction."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert "sec:intro" in tex.labels
    assert "sec:method" in tex.labels
    assert "sec:results" in tex.labels
    assert "fig:architecture" in tex.refs
    assert "tab:results" in tex.refs
    assert "fig:missing" in tex.refs


def test_parse_tex_extended_refs(tmp_path):
    """cleveref/autoref variants and ranges should be parsed."""
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\begin{document}
\Cref{fig:a,tab:b}
\crefrange{eq:start}{eq:end}
\subref{fig:sub}
\pageref{sec:appendix}
\nameref{sec:intro}
\namecref{fig:name}
\cpageref{tab:pages}
\end{document}
""",
        encoding="utf-8",
    )

    tex = parse_tex_file(tex_path)
    assert tex.refs == [
        "fig:a",
        "tab:b",
        "fig:sub",
        "sec:appendix",
        "sec:intro",
        "fig:name",
        "tab:pages",
        "eq:start",
        "eq:end",
    ]


def test_parse_tex_inputs_and_graphics():
    """Test input and graphics extraction."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert "tables/results" in tex.inputs
    assert "figures/architecture.png" in tex.graphics


def test_parse_tex_graphics_extensionless_paths_and_comments(tmp_path):
    """Graphics parser should keep extensionless paths and ignore comments."""
    tex_path = tmp_path / "main.tex"
    tex_path.write_text(
        r"""
\documentclass{article}
\begin{document}
\includegraphics{plot}
\includegraphics[width=0.8\textwidth]{figures/chart}
% \includegraphics{ignored}
\end{document}
""",
        encoding="utf-8",
    )

    tex = parse_tex_file(tex_path)

    assert tex.graphics == ["plot", "figures/chart"]
    assert "ignored" not in tex.graphics


def test_parse_tex_sections():
    """Test section title extraction."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert "Introduction" in tex.sections
    assert "Method" in tex.sections
    assert "Results" in tex.sections
    assert "Conclusion" in tex.sections


def test_parse_bib_entries():
    """Test that bib parser extracts all entries correctly."""
    entries = parse_bib_file(FIXTURES / "sample_fake.bib")
    assert len(entries) == 4

    keys = {e.key for e in entries}
    assert "fake_entry_1" in keys
    assert "fake_entry_2" in keys
    assert "real_entry_attention" in keys
    assert "real_entry_bert" in keys


def test_parse_bib_doi_detection():
    """Test that missing DOI is correctly identified."""
    entries = parse_bib_file(FIXTURES / "sample_fake.bib")
    entry_map = {e.key: e for e in entries}

    # fake_entry_1 has a fake DOI
    assert entry_map["fake_entry_1"].doi == "10.1234/fake.2023.99999"
    # fake_entry_2 has NO DOI
    assert entry_map["fake_entry_2"].doi is None
    # real entries have DOIs
    assert entry_map["real_entry_attention"].doi is not None
    assert entry_map["real_entry_bert"].doi is not None


def test_parse_bib_normalizes_doi_urls(tmp_path):
    """DOIs stored as URLs or doi: prefixes should be normalized."""
    bib_path = tmp_path / "refs.bib"
    bib_path.write_text(
        r"""
@article{url_doi,
  title={A Paper},
  author={Doe, Jane},
  year={2024},
  doi={https://doi.org/10.1234/ABC\_123.}
}
@article{prefix_doi,
  title={Another Paper},
  author={Doe, John},
  year={2024},
  doi={doi:10.5555/test;}
}
""",
        encoding="utf-8",
    )

    entries = {e.key: e for e in parse_bib_file(bib_path)}
    assert entries["url_doi"].doi == "10.1234/ABC_123"
    assert entries["prefix_doi"].doi == "10.5555/test"


def test_parse_bib_authors():
    """Test author name parsing."""
    entries = parse_bib_file(FIXTURES / "sample_fake.bib")
    entry_map = {e.key: e for e in entries}

    # Check fake entry has GPT-style author names
    fake_authors = entry_map["fake_entry_1"].authors
    assert len(fake_authors) == 3
    assert any("Whitmore" in a for a in fake_authors)

    # Check real entry
    bert_authors = entry_map["real_entry_bert"].authors
    assert len(bert_authors) == 4
    assert any("Devlin" in a for a in bert_authors)


# === ZIP extraction security ===

def test_extract_zip_skips_dangerous_files(tmp_path):
    """Executable files inside a zip must not be written to disk."""
    zip_path = tmp_path / "payload.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("paper/main.tex", "\\documentclass{article}")
        zf.writestr("paper/evil.exe", "MZ binary")
        zf.writestr("paper/run.sh", "#!/bin/sh\nrm -rf /")
        zf.writestr("paper/macro.docm", "macro payload")

    dest = tmp_path / "out"
    root = extract_zip(zip_path, dest)

    assert (root / "main.tex").exists()
    assert not (root / "evil.exe").exists()
    assert not (root / "run.sh").exists()
    assert not (root / "macro.docm").exists()


def test_extract_zip_blocks_path_traversal(tmp_path):
    """Zip Slip: a member escaping the destination must raise."""
    zip_path = tmp_path / "slip.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../escape.tex", "pwned")

    dest = tmp_path / "out"
    with pytest.raises(ValueError):
        extract_zip(zip_path, dest)
    assert not dest.exists()


def test_extract_zip_blocks_too_many_members(tmp_path):
    """Archives with excessive member counts are rejected before extraction."""
    zip_path = tmp_path / "many.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for i in range(2001):
            zf.writestr(f"paper/{i}.txt", "x")

    with pytest.raises(ValueError, match="too many files"):
        extract_zip(zip_path, tmp_path / "out")


def test_extract_zip_blocks_zip_bomb_ratio(tmp_path):
    """Highly-compressible huge members are rejected as suspicious."""
    zip_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("paper/main.tex", "A" * (1024 * 1024))

    with pytest.raises(ValueError, match="compression ratio"):
        extract_zip(zip_path, tmp_path / "out")


def test_extract_zip_blocks_deep_paths(tmp_path):
    """Extremely deep member paths are rejected to avoid path/resource abuse."""
    zip_path = tmp_path / "deep.zip"
    deep_name = "/".join(["paper", *[f"d{i}" for i in range(25)], "main.tex"])
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(deep_name, "\\documentclass{article}")

    with pytest.raises(ValueError, match="too deep"):
        extract_zip(zip_path, tmp_path / "out")


def test_extract_zip_blocks_symlink_entries(tmp_path):
    """Symlink entries must not be extracted."""
    zip_path = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("paper/link.tex")
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("paper/main.tex", "\\documentclass{article}")
        zf.writestr(info, "main.tex")

    with pytest.raises(ValueError, match="Symlink"):
        extract_zip(zip_path, tmp_path / "out")
