"""Lightweight writing style metrics for LaTeX papers."""

from __future__ import annotations

import re
from collections import Counter


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")


def _strip_latex(text: str) -> str:
    lines = []
    for line in text.splitlines():
        # Drop unescaped comments.
        line = re.sub(r"(?<!\\)%.*", "", line)
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\\begin\{(?:equation|align|table|figure|tabular|thebibliography)\*?\}.*?\\end\{\w+\*?\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\(?:cite\w*|ref|label|url|href)(?:\[[^\]]*\])*\{[^}]*\}", " ", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?\{([^}]*)\}", r" \1 ", text)
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = re.sub(r"[{}$&_~^#]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def analyze_writing_style(texts: list[str]) -> dict:
    """Return lexical diversity and sentence-complexity metrics."""
    clean = _strip_latex("\n".join(texts))
    words = [w.lower().strip("'-") for w in _WORD_RE.findall(clean)]
    words = [w for w in words if len(w) > 1]
    sentences = [
        _WORD_RE.findall(s)
        for s in _SENTENCE_RE.findall(clean)
        if _WORD_RE.search(s)
    ]

    word_count = len(words)
    unique_words = len(set(words))
    lexical_diversity = (unique_words / word_count) if word_count else 0.0
    sentence_lengths = [len(s) for s in sentences if s]
    avg_sentence_words = (sum(sentence_lengths) / len(sentence_lengths)) if sentence_lengths else 0.0
    long_sentence_count = sum(1 for n in sentence_lengths if n >= 30)
    long_sentence_pct = (long_sentence_count / len(sentence_lengths) * 100) if sentence_lengths else 0.0

    repeated = [
        {"word": word, "count": count}
        for word, count in Counter(words).most_common(10)
        if count >= 5 and len(word) > 4
    ][:5]

    hints: list[str] = []
    if word_count and lexical_diversity < 0.35:
        hints.append("词汇多样性偏低，可能显得重复，可替换高频泛化词。")
    if avg_sentence_words > 28:
        hints.append("平均句长偏长，建议拆分部分复杂句以提升可读性。")
    if long_sentence_pct > 20:
        hints.append("长句比例偏高，审稿人快速阅读时可能更吃力。")
    if not hints:
        hints.append("写作风格指标整体正常，可重点检查术语一致性和 claim 支撑。")

    return {
        "word_count": word_count,
        "unique_words": unique_words,
        "sentence_count": len(sentence_lengths),
        "lexical_diversity": round(lexical_diversity, 3),
        "avg_sentence_words": round(avg_sentence_words, 1),
        "long_sentence_count": long_sentence_count,
        "long_sentence_pct": round(long_sentence_pct, 1),
        "repeated_words": repeated,
        "hints": hints,
    }
