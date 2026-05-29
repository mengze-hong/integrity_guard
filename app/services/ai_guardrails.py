"""AI suggestion guardrails and reference-candidate helpers."""

from __future__ import annotations

import re

from app.config import settings

_REF_ISSUE_KEYWORDS = (
    "DOI 无法解析", "无法解析", "fabricat", "伪造", "retract", "撤稿",
    "无法验证", "未找到该文献", "不存在的文献", "虚构",
    "缺少 DOI", "无可信来源", "标题搜索未找到", "source not found",
    "Unverified reference", "official URL/DOI", "DOI/source not found",
)


def is_reference_authenticity_issue(gate_name: str = "", message: str = "") -> bool:
    """True if an issue concerns citation/reference authenticity."""
    if gate_name == "reference_authenticity":
        return True
    msg = message or ""
    return any(k in msg for k in _REF_ISSUE_KEYWORDS)


def ai_fix_provenance(gate_name: str, file_path: str, line_num, context: str) -> dict:
    """Return audit metadata for an AI suggestion."""
    return {
        "source": "llm",
        "model": settings.llm_model,
        "gate": gate_name,
        "file": file_path or None,
        "line": line_num,
        "context_chars": len(context or ""),
    }


def not_fixable_reference_payload(issue_message: str, gate_name: str = "") -> dict:
    """Standard response for reference issues that must not be LLM-fixed."""
    return {
        "status": "not_fixable",
        "not_fixable": True,
        "risk": "high",
        "requires_manual_review": True,
        "provenance": {
            "source": "rule",
            "gate": gate_name or "reference_authenticity",
            "reason": "reference_authenticity_guardrail",
        },
        "detail": (
            "文献真实性/缺少可信来源的问题不提供 AI 建议修复。"
            "请删除该引用，或替换为可在 Crossref / Semantic Scholar / OpenAlex "
            "等权威来源核实的真实文献；不要使用 AI 编造 BibTeX。"
        ),
        "candidate_search_available": True,
        "issue": issue_message,
    }


def extract_reference_title(*texts: str) -> str:
    """Best-effort extraction of a reference title from issue/evidence text."""
    blob = "\n".join(t for t in texts if t)
    patterns = [
        r"标题[:：]\s*(.+)",
        r"title[:：]\s*(.+)",
        r"\\btitle\\s*=\\s*[{\"]([^}\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, blob, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("{}\"'.,;")[:300]
    return ""


def candidate_from_crossref(item: dict) -> dict:
    title = (item.get("title") or [""])[0]
    authors = [
        " ".join(part for part in [a.get("given", ""), a.get("family", "")] if part).strip()
        for a in item.get("author", [])[:5]
    ]
    year_parts = (item.get("issued") or {}).get("date-parts") or []
    year = year_parts[0][0] if year_parts and year_parts[0] else None
    doi = item.get("DOI")
    return {
        "source": "crossref",
        "title": title,
        "authors": [a for a in authors if a],
        "year": year,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else item.get("URL"),
        "score": item.get("score"),
    }


def candidate_from_s2(item: dict) -> dict:
    return {
        "source": "semantic_scholar",
        "title": item.get("title"),
        "authors": [a.get("name") for a in item.get("authors", [])[:5] if a.get("name")],
        "year": item.get("year"),
        "doi": item.get("externalIds", {}).get("DOI"),
        "url": item.get("url"),
        "score": None,
    }


def candidate_from_openalex(item: dict) -> dict:
    doi = item.get("doi")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.removeprefix("https://doi.org/")
    return {
        "source": "openalex",
        "title": item.get("display_name"),
        "authors": [
            a.get("author", {}).get("display_name")
            for a in item.get("authorships", [])[:5]
            if a.get("author", {}).get("display_name")
        ],
        "year": item.get("publication_year"),
        "doi": doi,
        "url": item.get("id"),
        "score": item.get("relevance_score"),
    }
