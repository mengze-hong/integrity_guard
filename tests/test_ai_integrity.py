"""Tests for AI suggestion integrity guardrails."""

from app.api.routes import (
    _candidate_from_crossref,
    _extract_reference_title,
    _is_reference_authenticity_issue,
    _not_fixable_reference_payload,
)


def test_reference_authenticity_issue_is_not_fixable_payload():
    payload = _not_fixable_reference_payload(
        "[fake_entry_2] 缺少 DOI 且无可信来源，标题搜索未找到匹配",
        "reference_authenticity",
    )

    assert _is_reference_authenticity_issue("reference_authenticity", payload["issue"])
    assert payload["status"] == "not_fixable"
    assert payload["not_fixable"] is True
    assert payload["candidate_search_available"] is True
    assert "suggestion" not in payload
    assert payload["provenance"]["source"] == "rule"


def test_non_reference_issue_is_ai_fixable():
    assert not _is_reference_authenticity_issue(
        "figure_table_crossref",
        "Figure 1 is never referenced in text",
    )


def test_extract_reference_title_from_evidence():
    assert (
        _extract_reference_title("问题", "标题: Transformer-based Approach for Verification")
        == "Transformer-based Approach for Verification"
    )


def test_candidate_from_crossref_uses_authoritative_metadata():
    candidate = _candidate_from_crossref({
        "title": ["Attention Is All You Need"],
        "author": [{"given": "Ashish", "family": "Vaswani"}],
        "issued": {"date-parts": [[2017]]},
        "DOI": "10.5555/3295222.3295349",
        "score": 12.3,
    })

    assert candidate["source"] == "crossref"
    assert candidate["doi"] == "10.5555/3295222.3295349"
    assert candidate["authors"] == ["Ashish Vaswani"]
