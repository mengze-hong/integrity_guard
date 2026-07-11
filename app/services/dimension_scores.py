"""Derived multi-dimensional paper scores from quality gate results."""

from __future__ import annotations

from app.models import FullReport


def _gate_scores(report: FullReport) -> dict[str, float]:
    return {gate.gate_name: float(gate.score) for gate in report.gate_results}


def _avg(scores: dict[str, float], names: list[str], fallback: float) -> float:
    values = [scores[name] for name in names if name in scores]
    if not values:
        return fallback
    return sum(values) / len(values)


def build_dimension_scores(report: FullReport) -> dict:
    """Build reviewer-like dimensions from existing deterministic gates.

    These are derived product heuristics, not a claim that novelty or
    significance can be fully measured without expert review.
    """
    scores = _gate_scores(report)
    overall = float(report.overall_score or 0)

    dimensions = [
        {
            "key": "novelty",
            "label": "Novelty",
            "score": _avg(scores, ["reference_authenticity"], overall),
            "basis": "Reference authenticity & citation freshness signal",
        },
        {
            "key": "soundness",
            "label": "Soundness",
            "score": _avg(scores, ["data_integrity", "citation_bib_consistency", "reference_authenticity"], overall),
            "basis": "Data integrity, citation consistency & reference authenticity",
        },
        {
            "key": "clarity",
            "label": "Clarity",
            "score": _avg(scores, ["writing_quality", "figure_table_crossref", "structure_integrity"], overall),
            "basis": "Writing quality, figure cross-references & structure",
        },
        {
            "key": "significance",
            "label": "Significance",
            "score": _avg(scores, ["data_integrity", "writing_quality", "reference_authenticity"], overall),
            "basis": "Result credibility, clarity & literature support",
        },
    ]

    for item in dimensions:
        item["score"] = round(max(0.0, min(100.0, item["score"])), 1)

    return {
        "summary": "Heuristic reviewer-style dimensions derived from ScholarLint gates.",
        "dimensions": dimensions,
    }
