"""Tests for LaTeX format normalization helpers."""

from app.tools.format_normalizer import normalize_format


def test_normalize_format_fixes_common_latex_spacing():
    text = (
        "See Table 1 and Figure 2.  Extra spaces here.   \n"
        "Fig. \\ref{fig:a} and Eq. \\ref{eq:a}%comment\n"
        "\n\n\n"
        "\\url{https://example.com/a%b}\n"
    )

    normalized, changes = normalize_format(text)

    assert "Table~1" in normalized
    assert "Figure~2" in normalized
    assert "Extra spaces here." in normalized
    assert "Fig.~\\ref{fig:a}" in normalized
    assert "Eq.~\\ref{eq:a}" in normalized
    assert "Eq.~\\ref{eq:a}% comment" in normalized
    assert "\n\n\n" not in normalized
    assert "\\url{https://example.com/a%b}" in normalized
    assert any("统一非断行空格" in change for change in changes)
    assert any("去除行尾空格" in change for change in changes)
    assert any("压缩多余空行" in change for change in changes)


def test_normalize_format_unifies_only_bare_cite_commands():
    text = (
        "Prior work \\cite{alpha} and \\cite[see][p. 3]{beta}.\n"
        "Textual \\citet{gamma} and parenthetical \\citep{delta} stay.\n"
        "% Commented \\cite{skip} stays untouched.\n"
    )

    normalized, changes = normalize_format(text)

    assert "\\citep{alpha}" in normalized
    assert "\\citep[see][p. 3]{beta}" in normalized
    assert "\\citet{gamma}" in normalized
    assert "\\citep{delta}" in normalized
    assert "% Commented \\cite{skip}" in normalized
    assert any("统一引用命令" in change for change in changes)
