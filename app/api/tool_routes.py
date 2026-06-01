"""Editor-side tool endpoints split out of ``app.api.routes``.

This module owns project-mutating helpers that the editor toolbar surfaces
(bib cleanup, fetch official .bib by DOI, real-reference candidate search,
tidy-up dry-run/apply, and source-file format normalization).

Why a separate file? ``routes.py`` grew into a god-module mixing upload,
report, AI batch, files, tools, history, dashboard, and admin endpoints,
which made it hard for a new engineer to find and reason about a single
feature. The slice is structural only: URLs, payloads, and behavior are
identical to v5.3.93. Permission checks, in-memory state, and AI guardrails
are reused via imports from ``app.api.routes`` and ``app.services``.

Mounted alongside the legacy router in ``app/main.py`` under the same
``/api`` prefix.
"""

from __future__ import annotations

import httpx

from fastapi import APIRouter, HTTPException, Request, Response

from app.config import settings
from app.services.file_store import safe_project_file
from app.services.ai_guardrails import (
    candidate_from_crossref as _candidate_from_crossref,
    candidate_from_openalex as _candidate_from_openalex,
    candidate_from_s2 as _candidate_from_s2,
    extract_reference_title as _extract_reference_title,
)

# Reuse the legacy module for permission / state helpers so a single source
# of truth still owns access control and the in-memory job index.
from app.api import routes as _legacy
from app.api.routes import _require_job_access, _get_report, _job_dirs

router = APIRouter()


# ─── .bib cleanup ─────────────────────────────────────────────


@router.post("/bib-clean/{job_id}")
async def clean_bib(job_id: str, request: Request, response: Response):
    """Clean / sort / partition a project's .bib files.

    The request body's ``action`` selects the operation:

    - ``clean`` (default): normalize whitespace, braces, etc.
    - ``sort``: reorder entries to follow the citation order in the .tex.
    - ``separate_unused``: move never-cited entries to ``unused.bib``.
    - ``all``: clean → dedupe → sort → separate (full cleanup).
    """
    await _require_job_access(job_id, request, response, write=True)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    action = body.get("action", "clean")

    from app.tools.bib_cleaner import (
        clean_bib_text,
        sort_bib_by_citation_order,
        separate_unused,
        deduplicate_entries,
    )
    from app.parsers.tex_parser import parse_all_tex_files

    bib_files = list(project_dir.rglob("*.bib"))
    if not bib_files:
        raise HTTPException(status_code=404, detail="No .bib file found")

    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    results = {}
    for bib_path in bib_files:
        if bib_path.name == "unused.bib":
            continue
        original = bib_path.read_text(encoding="utf-8", errors="replace")
        rel_path = str(bib_path.relative_to(project_dir)).replace("\\", "/")

        if action == "clean":
            cleaned = clean_bib_text(original)
            bib_path.write_text(cleaned, encoding="utf-8")
            results[rel_path] = {
                "action": "cleaned",
                "size_before": len(original),
                "size_after": len(cleaned),
            }

        elif action == "sort":
            sorted_text = sort_bib_by_citation_order(original, tex_files)
            bib_path.write_text(sorted_text, encoding="utf-8")
            results[rel_path] = {"action": "sorted_by_citation_order"}

        elif action == "separate_unused":
            used_text, unused_text = separate_unused(original, tex_files)
            bib_path.write_text(used_text, encoding="utf-8")
            if unused_text:
                unused_path = bib_path.parent / "unused.bib"
                unused_path.write_text(unused_text, encoding="utf-8")
                results[rel_path] = {
                    "action": "separated",
                    "unused_file": "unused.bib",
                    "unused_entries": unused_text.count("@"),
                }
            else:
                results[rel_path] = {"action": "no_unused_entries"}

        elif action == "all":
            cleaned = clean_bib_text(original)
            deduped, num_removed = deduplicate_entries(cleaned)
            sorted_text = sort_bib_by_citation_order(deduped, tex_files)
            used_text, unused_text = separate_unused(sorted_text, tex_files)
            bib_path.write_text(used_text, encoding="utf-8")
            if unused_text:
                unused_path = bib_path.parent / "unused.bib"
                unused_path.write_text(unused_text, encoding="utf-8")
            results[rel_path] = {
                "action": "full_cleanup",
                "size_before": len(original),
                "size_after": len(used_text),
                "duplicates_removed": num_removed,
                "unused_entries": unused_text.count("@") if unused_text else 0,
            }

    return {"status": "done", "results": results}


# ─── Authoritative reference lookups (no LLM, no fabrication) ──


@router.get("/fetch-bib/{doi:path}")
async def fetch_official_bib(doi: str):
    """Fetch the official .bib entry for a DOI from DBLP / ACL / Crossref.

    Read-only; not job-scoped (no leakage risk). Never invokes an LLM.
    """
    sources = [f"https://dblp.org/doi/{doi}.bib"]

    from app.tools.bib_cleaner import clean_bib_text

    if "10.18653" in doi:
        acl_id = doi.split("/")[-1]
        sources.insert(0, f"https://aclanthology.org/{acl_id}.bib")

    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in sources:
            try:
                resp = await client.get(url)
                if resp.status_code == 200 and "@" in resp.text:
                    cleaned = clean_bib_text(resp.text.strip())
                    return {"status": "found", "source": url, "bib": cleaned.strip()}
            except Exception:
                continue

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex",
                headers={"User-Agent": f"ScholarLint/5.3 (mailto:{settings.crossref_email})"},
            )
            if resp.status_code == 200 and "@" in resp.text:
                cleaned = clean_bib_text(resp.text.strip())
                return {"status": "found", "source": "crossref", "bib": cleaned.strip()}
    except Exception:
        pass

    return {"status": "not_found", "doi": doi}


@router.post("/reference-candidates/{job_id}")
async def search_reference_candidates(job_id: str, request: Request, response: Response):
    """Return real candidate references for a suspect citation.

    Hard rule (do not relax): this endpoint never calls the LLM and never
    fabricates bibliography data. It only forwards public scholarly indexes
    (Crossref, Semantic Scholar, OpenAlex) so the author can pick a real
    replacement manually. ``allow_share=False`` keeps share-readonly viewers
    out — only the project owner triggers external lookups.
    """
    await _require_job_access(job_id, request, response, allow_share=False)
    body = await request.json()
    title = (body.get("title") or "").strip()
    if not title:
        title = _extract_reference_title(
            body.get("message", ""),
            body.get("evidence", ""),
            body.get("bibtex", ""),
        )
    if not title or len(title) < 8:
        return {
            "status": "not_found",
            "detail": "未能从问题中提取足够明确的标题，请手动输入标题后再搜索。",
            "candidates": [],
        }

    candidates = []
    scholarly_headers = {"User-Agent": "ScholarLint/5.3 (mailto:integrity@check.org)"}
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={"query.title": title, "rows": 3},
                headers={"User-Agent": f"ScholarLint/5.3 (mailto:{settings.crossref_email})"},
            )
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                candidates.extend(_candidate_from_crossref(item) for item in items)
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": title,
                    "limit": 3,
                    "fields": "title,authors,year,url,externalIds",
                },
                headers=scholarly_headers,
            )
            if resp.status_code == 200:
                candidates.extend(_candidate_from_s2(item) for item in resp.json().get("data", []))
        except Exception:
            pass

        try:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={"search": title, "per-page": 3},
                headers=scholarly_headers,
            )
            if resp.status_code == 200:
                candidates.extend(_candidate_from_openalex(item) for item in resp.json().get("results", []))
        except Exception:
            pass

    seen = set()
    deduped = []
    for candidate in candidates:
        if not candidate.get("title"):
            continue
        key = (candidate.get("doi") or candidate.get("title", "")).lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return {
        "status": "ok" if deduped else "not_found",
        "query": title,
        "candidates": deduped[:8],
        "provenance": {
            "source": "authoritative_search",
            "sources": ["crossref", "semantic_scholar", "openalex"],
            "llm_used": False,
        },
    }


# ─── Project tidy-up (dry-run + execute) ──────────────────────


@router.get("/tidyup/{job_id}")
async def analyze_tidyup_changes(job_id: str, request: Request, response: Response):
    """Preview tidy-up actions without modifying the project."""
    await _require_job_access(job_id, request, response, write=True)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.tools.tidyup import analyze_tidyup
    from app.parsers.tex_parser import parse_all_tex_files

    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    changes = analyze_tidyup(project_dir, tex_files)
    return {
        "changes": [
            {
                "type": c["type"],
                "description": c["description"],
                "source": c["source"],
                "target": c["target"],
            }
            for c in changes
        ]
    }


@router.post("/tidyup/{job_id}")
async def execute_tidyup(job_id: str, request: Request, response: Response):
    """Apply the user-selected tidy-up actions.

    Body ``selected`` is a list of indices into the most recent dry-run
    output. Indices outside that range are silently skipped to keep the
    endpoint robust against client/state drift.
    """
    await _require_job_access(job_id, request, response, write=True)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    selected_indices = body.get("selected", [])

    from app.tools.tidyup import analyze_tidyup, execute_changes
    from app.parsers.tex_parser import parse_all_tex_files

    tex_paths = list(project_dir.rglob("*.tex"))
    tex_files = parse_all_tex_files(tex_paths)

    all_changes = analyze_tidyup(project_dir, tex_files)
    selected_changes = [all_changes[i] for i in selected_indices if i < len(all_changes)]
    executed = execute_changes(project_dir, selected_changes)

    return {"status": "done", "executed": executed, "count": len(executed)}


# ─── Format normalization ─────────────────────────────────────


@router.post("/format-normalize/{job_id}")
async def format_normalize(job_id: str, request: Request, response: Response):
    """Auto-fix formatting inconsistencies in .tex files.

    Body fields:

    - ``file`` (optional): a project-relative .tex file. If omitted, every
      .tex file is processed.
    - ``rules`` (optional): a list of normalization rule names. ``None``
      runs every rule the normalizer ships with.
    """
    await _require_job_access(job_id, request, response, write=True)
    if job_id not in _job_dirs:
        _get_report(job_id)
    project_dir = _job_dirs.get(job_id)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    body = await request.json()
    file_path = body.get("file")
    rules = body.get("rules")

    from app.tools.format_normalizer import normalize_format

    all_changes = []
    targets = []

    if file_path:
        target = safe_project_file(project_dir, file_path, allowed_suffixes=(".tex",))
        if target.exists() and target.suffix == ".tex":
            targets.append(target)
    else:
        targets = list(project_dir.rglob("*.tex"))

    for target in targets:
        content = target.read_text(encoding="utf-8")
        normalized, changes = normalize_format(content, rules)
        if changes:
            target.write_text(normalized, encoding="utf-8")
            all_changes.extend([f"[{target.name}] {c}" for c in changes])

    return {
        "status": "ok",
        "changes": all_changes,
        "files_modified": len([t for t in targets if any(t.name in c for c in all_changes)]),
    }


# Touch the legacy module so any test harness that still imports it side by
# side keeps a live reference; FastAPI decorators leave the function names
# intact in this module's globals (e.g. ``clean_bib`` is still callable).
_ = _legacy
