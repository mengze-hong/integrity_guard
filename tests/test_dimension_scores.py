"""Tests for derived multi-dimensional scores."""

from app.models import CheckResult, FullReport
from app.services.dimension_scores import build_dimension_scores


def test_build_dimension_scores_uses_gate_scores_and_bounds_values():
    report = FullReport(
        job_id="job",
        filename="paper.zip",
        overall_score=70,
        gate_results=[
            CheckResult(gate_name="reference_authenticity", gate_description="ref", passed=True, score=100, summary=""),
            CheckResult(gate_name="data_integrity", gate_description="data", passed=False, score=40, summary=""),
            CheckResult(gate_name="citation_bib_consistency", gate_description="cite", passed=True, score=80, summary=""),
            CheckResult(gate_name="writing_quality", gate_description="write", passed=True, score=60, summary=""),
            CheckResult(gate_name="figure_table_crossref", gate_description="fig", passed=True, score=90, summary=""),
            CheckResult(gate_name="structure_integrity", gate_description="struct", passed=True, score=75, summary=""),
        ],
    )

    result = build_dimension_scores(report)

    dimensions = {item["key"]: item for item in result["dimensions"]}
    assert set(dimensions) == {"novelty", "soundness", "clarity", "significance"}
    assert dimensions["novelty"]["score"] == 100
    assert dimensions["soundness"]["score"] == 73.3
    assert dimensions["clarity"]["score"] == 75
    assert dimensions["significance"]["score"] == 66.7
    assert all(0 <= item["score"] <= 100 for item in dimensions.values())


def test_build_dimension_scores_falls_back_to_overall_score():
    report = FullReport(job_id="job", filename="paper.zip", overall_score=66)

    result = build_dimension_scores(report)

    assert [item["score"] for item in result["dimensions"]] == [66, 66, 66, 66]
