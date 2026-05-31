"""Tests for lightweight writing style analysis."""

from app.services.style_analysis import analyze_writing_style


def test_analyze_writing_style_reports_diversity_and_sentence_complexity():
    text = r"""
\section{Introduction}
This method improves robustness and clarity. This method improves robustness and clarity.
This extremely long sentence contains many repeated research words and many repeated research words and many repeated research words and many repeated research words and many repeated research words and many repeated research words.
% This comment should not count repeated repeated repeated repeated repeated.
\cite{skip} \ref{fig:skip}
"""

    metrics = analyze_writing_style([text])

    assert metrics["word_count"] > 20
    assert metrics["unique_words"] > 0
    assert metrics["sentence_count"] == 3
    assert metrics["avg_sentence_words"] > 0
    assert metrics["long_sentence_count"] == 1
    assert any(item["word"] == "repeated" for item in metrics["repeated_words"])
    assert all("comment" not in hint.lower() for hint in metrics["hints"])


def test_analyze_writing_style_handles_empty_text():
    metrics = analyze_writing_style(["% only comments\n\\cite{x}"])

    assert metrics["word_count"] == 0
    assert metrics["lexical_diversity"] == 0
    assert metrics["avg_sentence_words"] == 0
    assert metrics["hints"]
