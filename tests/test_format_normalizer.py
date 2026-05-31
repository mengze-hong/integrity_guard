"""Tests for LaTeX format normalization helpers."""

from app.tools.format_normalizer import normalize_format


def test_normalize_format_fixes_common_latex_spacing():
    text = (
        "See Table 1 and Figure 2.  Extra spaces here.   \n"
        "Fig. \\ref{fig:a} and Eq. \\ref{eq:a}%comment\n"
        "\\url{https://example.com/a%b}\n"
    )

    normalized, changes = normalize_format(text)

    assert "Table~1" in normalized
    assert "Figure~2" in normalized
    assert "Extra spaces here." in normalized
    assert "Fig.~\\ref{fig:a}" in normalized
    assert "Eq.~\\ref{eq:a}" in normalized
    assert "Eq.~\\ref{eq:a}% comment" in normalized
    assert "\\url{https://example.com/a%b}" in normalized
    assert any("统一非断行空格" in change for change in changes)
    assert any("去除行尾空格" in change for change in changes)
