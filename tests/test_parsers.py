"""Tests for parsers module."""

from pathlib import Path

from app.parsers.tex_parser import parse_tex_file
from app.parsers.bib_parser import parse_bib_file


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


def test_parse_tex_labels_and_refs():
    """Test label and ref extraction."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert "sec:intro" in tex.labels
    assert "sec:method" in tex.labels
    assert "sec:results" in tex.labels
    assert "fig:architecture" in tex.refs
    assert "tab:results" in tex.refs
    assert "fig:missing" in tex.refs


def test_parse_tex_inputs_and_graphics():
    """Test input and graphics extraction."""
    tex = parse_tex_file(FIXTURES / "sample_main.tex")
    assert "tables/results" in tex.inputs
    assert "figures/architecture.png" in tex.graphics


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
