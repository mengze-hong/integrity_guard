"""Tests for AI suggestion integrity guardrails."""

from pathlib import Path

from app.api.routes import (
    _collect_batch_fix_candidates,
    _is_reference_authenticity_issue,
    _not_fixable_reference_payload,
)
from app.services.ai_guardrails import (
    candidate_from_crossref as _candidate_from_crossref,
    extract_reference_title as _extract_reference_title,
)
from app.models import CheckResult, DismissedIssue, FullReport, Issue, Severity
from app.services.ai_reports import (
    build_diagnosis_payload,
    fallback_diagnosis,
    parse_diagnosis_response,
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


def _batch_report(*gates: CheckResult, dismissed: list[DismissedIssue] | None = None) -> FullReport:
    return FullReport(
        job_id="job-test",
        filename="paper.zip",
        gate_results=list(gates),
        dismissed_issues=dismissed or [],
    )


def test_batch_fix_candidates_skip_reference_authenticity(tmp_path: Path):
    (tmp_path / "main.tex").write_text("A fake citation \\cite{fake}.\n", encoding="utf-8")
    report = _batch_report(CheckResult(
        gate_name="reference_authenticity",
        gate_description="refs",
        passed=False,
        score=0,
        issues=[
            Issue(
                severity=Severity.ERROR,
                message="[fake] DOI 无法解析，标题搜索未找到匹配",
                file="main.tex",
                line=1,
            )
        ],
    ))

    candidates, summary, skipped = _collect_batch_fix_candidates(report, tmp_path)

    assert candidates == []
    assert summary["total_error_issues"] == 1
    assert summary["total_fixable"] == 0
    assert summary["skipped"]["reference_authenticity"] == 1
    assert skipped[0]["reason"] == "reference_authenticity"


def test_batch_fix_candidates_skip_dismissed_issue(tmp_path: Path):
    (tmp_path / "main.tex").write_text("\\begin{figure}\n\\end{figure}\n", encoding="utf-8")
    issue = Issue(
        severity=Severity.ERROR,
        message="Figure is missing a label",
        file="main.tex",
        line=1,
    )
    report = _batch_report(
        CheckResult(
            gate_name="figure_table_crossref",
            gate_description="figures",
            passed=False,
            score=0,
            issues=[issue],
        ),
        dismissed=[
            DismissedIssue(
                gate_name="figure_table_crossref",
                issue_index=0,
                reason="template handles labels",
                original_message=issue.message,
                severity=Severity.ERROR,
            )
        ],
    )

    candidates, summary, skipped = _collect_batch_fix_candidates(report, tmp_path)

    assert candidates == []
    assert summary["skipped"]["dismissed"] == 1
    assert skipped[0]["reason"] == "dismissed"


def test_batch_fix_candidates_return_provenance_inputs_by_gate(tmp_path: Path):
    (tmp_path / "main.tex").write_text(
        "\\begin{figure}\n\\caption{System overview}\n\\end{figure}\n",
        encoding="utf-8",
    )
    report = _batch_report(CheckResult(
        gate_name="figure_table_crossref",
        gate_description="figures",
        passed=False,
        score=0,
        issues=[
            Issue(
                severity=Severity.ERROR,
                message="Figure has NO \\label",
                suggestion="Add a label after the caption.",
                file="main.tex",
                line=2,
            )
        ],
    ))

    candidates, summary, skipped = _collect_batch_fix_candidates(report, tmp_path)

    assert skipped == []
    assert summary["total_fixable"] == 1
    assert summary["selected_for_generation"] == 1
    assert summary["by_gate"]["figure_table_crossref"]["fixable"] == 1
    assert candidates[0]["gate_name"] == "figure_table_crossref"
    assert candidates[0]["issue_index"] == 0
    assert candidates[0]["file"] == "main.tex"
    assert "System overview" in candidates[0]["context"]


def test_diagnosis_payload_excludes_internal_project_path():
    report = _batch_report(CheckResult(
        gate_name="writing_quality",
        gate_description="writing",
        passed=False,
        score=60,
        summary="Writing issues found",
        issues=[
            Issue(
                severity=Severity.ERROR,
                message="Abstract and conclusion are too similar",
                suggestion="Rewrite the conclusion to emphasize findings.",
                file="main.tex",
                line=12,
            )
        ],
    ))
    report.project_dir = "C:/Users/example/private/job"
    report.metadata = {
        "word_count": 1234,
        "project_dir": "C:/Users/example/private/job",
        "owner_id": "secret-owner",
    }

    payload = build_diagnosis_payload(report)

    assert payload["metadata"] == {"word_count": 1234}
    assert "project_dir" not in str(payload)
    assert "secret-owner" not in str(payload)
    assert payload["top_issues"][0]["gate_name"] == "writing_quality"


def test_parse_diagnosis_response_accepts_json_fence():
    payload = {"overall_score": 80, "issue_counts": {"errors": 1, "warnings": 2}, "top_issues": []}
    text = """```json
{
  "summary": "Needs revision.",
  "top_priorities": [],
  "quick_wins": ["Fix anchored issues."],
  "estimated_time": "30 minutes",
  "risk_notes": ["Verify AI advice."],
  "next_actions": ["Open workspace."]
}
```"""

    diagnosis, used_fallback = parse_diagnosis_response(text, payload)

    assert used_fallback is False
    assert diagnosis["summary"] == "Needs revision."


def test_parse_diagnosis_response_falls_back_on_bad_json():
    payload = {
        "overall_score": 50,
        "issue_counts": {"errors": 2, "warnings": 1},
        "top_issues": [
            {
                "gate_name": "figure_table_crossref",
                "severity": "error",
                "message": "Figure is not referenced",
                "suggestion": "Reference the figure in the text.",
                "file": "main.tex",
                "line": 4,
            }
        ],
    }

    diagnosis, used_fallback = parse_diagnosis_response("not json", payload)

    assert used_fallback is True
    assert diagnosis == fallback_diagnosis(payload)
    assert diagnosis["top_priorities"][0]["target"] == "main.tex:4"
