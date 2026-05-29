"""Helpers for AI-generated paper diagnosis reports."""

from __future__ import annotations

import json
from typing import Any

from app.models import FullReport, Severity

DIAGNOSIS_SCHEMA_KEYS = {
    "summary",
    "top_priorities",
    "quick_wins",
    "estimated_time",
    "risk_notes",
    "next_actions",
}


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep user-facing report statistics and drop internal paths/secrets."""
    allowed = {
        "word_count",
        "page_estimate",
        "bib_count",
        "tex_count",
        "figure_count",
        "table_count",
        "citation_count",
    }
    return {k: metadata[k] for k in allowed if k in metadata}


def build_diagnosis_payload(report: FullReport, *, max_issues: int = 12) -> dict[str, Any]:
    """Build a compact, non-sensitive diagnosis payload from gate results."""
    gates = []
    top_issues = []
    for gate in report.gate_results:
        error_count = sum(1 for issue in gate.issues if issue.severity == Severity.ERROR)
        warning_count = sum(1 for issue in gate.issues if issue.severity == Severity.WARNING)
        gates.append({
            "gate_name": gate.gate_name,
            "passed": gate.passed,
            "score": gate.score,
            "summary": gate.summary,
            "error_count": error_count,
            "warning_count": warning_count,
        })
        for idx, issue in enumerate(gate.issues):
            if len(top_issues) >= max_issues:
                break
            if issue.severity not in {Severity.ERROR, Severity.WARNING}:
                continue
            top_issues.append({
                "gate_name": gate.gate_name,
                "issue_index": idx,
                "severity": issue.severity.value,
                "message": issue.message,
                "suggestion": issue.suggestion or "",
                "file": issue.file or "",
                "line": issue.line,
            })

    return {
        "filename": report.filename,
        "overall_score": report.overall_score,
        "overall_passed": report.overall_passed,
        "metadata": _safe_metadata(report.metadata or {}),
        "gates": gates,
        "top_issues": top_issues,
        "issue_counts": {
            "errors": sum(1 for gate in report.gate_results for issue in gate.issues if issue.severity == Severity.ERROR),
            "warnings": sum(1 for gate in report.gate_results for issue in gate.issues if issue.severity == Severity.WARNING),
            "dismissed": len(report.dismissed_issues),
        },
    }


def fallback_diagnosis(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic diagnosis when the LLM is unavailable or malformed."""
    issues = payload.get("top_issues") or []
    priorities = []
    for issue in issues[:3]:
        priorities.append({
            "title": issue.get("message", "Fix reported issue"),
            "reason": f"{issue.get('gate_name', 'gate')} reported a {issue.get('severity', 'risk')} issue.",
            "action": issue.get("suggestion") or "Open the issue in the workspace and apply a verified fix.",
            "target": f"{issue.get('file') or 'project'}:{issue.get('line') or '?'}",
        })

    if not priorities:
        priorities.append({
            "title": "Review remaining warnings",
            "reason": "No blocking errors were found in the summarized report.",
            "action": "Check warnings and rerun quality checks before submission.",
            "target": "overview",
        })

    counts = payload.get("issue_counts") or {}
    return {
        "summary": (
            f"Current score is {payload.get('overall_score', 0):.0f}/100 with "
            f"{counts.get('errors', 0)} errors and {counts.get('warnings', 0)} warnings."
        ),
        "top_priorities": priorities,
        "quick_wins": [
            "Fix issues with exact file and line anchors first.",
            "Rerun checks after each batch of accepted suggestions.",
            "Do not accept AI changes that alter claims, numbers, or references without verification.",
        ],
        "estimated_time": "30-90 minutes depending on how many anchored fixes can be applied directly.",
        "risk_notes": [
            "AI suggestions are advisory and require author review.",
            "Reference authenticity issues must be resolved with authoritative sources.",
        ],
        "next_actions": [
            "Open the workspace and resolve the top priority issues.",
            "Use batch suggestions only when the original snippet still matches.",
            "Export or share the report after a clean recheck.",
        ],
    }


def parse_diagnosis_response(text: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Parse a model JSON response, falling back to deterministic output."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "```", 1)
        raw = raw.removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except Exception:
        return fallback_diagnosis(payload), True

    if not isinstance(data, dict) or not DIAGNOSIS_SCHEMA_KEYS.issubset(data.keys()):
        return fallback_diagnosis(payload), True
    return data, False
