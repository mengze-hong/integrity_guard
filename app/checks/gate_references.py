"""Gate 2: 引文真实性验证（严格模式）

每条 .bib 引文通过 Crossref/DataCite 交叉验证：
1. DOI 必须存在
2. DOI 必须能在 Crossref 或 DataCite 解析
3. 标题标准化后必须 100% 匹配
4. 作者姓氏必须逐位对应
5. 期刊/会议名验证
6. 返回每条引文的验证链接
"""

import asyncio
import re
from difflib import SequenceMatcher

import httpx

from app.checks.base import BaseGate
from app.models import BibEntry, CheckResult, Issue, ParsedPaper, Severity

_TRANSIENT_SOURCES = {"crossref_unavailable", "datacite_unavailable", "s2_unavailable"}

# Key patterns that indicate AI model cards / tech reports (no DOI expected)
_TECH_REPORT_KEY_RE = re.compile(
    r"(?:chatgpt|claude|gpt[-_]?\d|gemini|llama|mistral|palm|bard|copilot|"
    r"qwen|deepseek|phi[-_]?\d|falcon|bloom|codex|dalle|midjourney|"
    r"openai|anthropic|google|meta[-_]?ai|microsoft)[-_]?\d*",
    re.IGNORECASE,
)
_TECH_REPORT_FIELDS = re.compile(
    r"technical\s+report|blog\s+post|model\s+card|white\s*paper|"
    r"system\s+report|press\s+release|private\s+communication|personal\s+communication",
    re.IGNORECASE,
)


def _normalize_title(s: str) -> str:
    """标准化标题用于精确比较。去除大小写、标点、LaTeX格式、多余空格。"""
    if not s:
        return ""
    s = s.lower()
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\textit", "").replace("\\textbf", "").replace("\\emph", "")
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _title_matches(a: str, b: str, threshold: float = 0.85) -> bool:
    """Return True if two normalized titles are close enough.

    Handles cases like 'socialiqa' vs 'social iqa' where spaces are stripped
    from a stylized title — we compare both the spaced and spaceless forms.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    # substring containment (subtitle truncation)
    if a in b or b in a:
        return True
    sim = SequenceMatcher(None, a, b).ratio()
    if sim >= threshold:
        return True
    # spaceless fallback: "socialiqa" ≈ "social iqa"
    a_ns = a.replace(" ", "")
    b_ns = b.replace(" ", "")
    if a_ns == b_ns:
        return True
    sim_ns = SequenceMatcher(None, a_ns, b_ns).ratio()
    return sim_ns >= threshold


def _extract_family_name(name: str) -> str:
    """提取作者姓氏。支持 'Last, First' 和 'First Last' 两种格式。"""
    import unicodedata
    name = name.strip()
    if not name:
        return ""
    if "," in name:
        family = name.split(",")[0].strip()
    else:
        parts = name.split()
        family = parts[-1] if parts else ""
    # Remove LaTeX formatting and normalize
    family = family.replace("{", "").replace("}", "").replace(".", "").replace("~", " ")
    family = re.sub(r'\\["\'^`~](\w)', r'\1', family)  # \"u → u, \'{e} → e
    family = re.sub(r"\\[a-zA-Z]+", "", family)  # Remove remaining commands
    # Normalize Unicode (ü → u, é → e, etc.)
    family = unicodedata.normalize("NFD", family)
    family = "".join(c for c in family if unicodedata.category(c) != "Mn")
    family = family.lower().strip()
    return family


class ReferenceAuthenticityGate(BaseGate):
    """Gate 2: 严格引文真实性验证"""

    name = "reference_authenticity"
    description = "引文真实性验证：通过 Crossref/DataCite 交叉验证每条引文的 DOI、标题、作者、期刊"
    is_blocking = True

    CROSSREF_BASE = "https://api.crossref.org"
    DATACITE_BASE = "https://api.datacite.org"
    S2_BASE = "https://api.semanticscholar.org/graph/v1"
    OPENALEX_BASE = "https://api.openalex.org"
    OPENREVIEW_BASE = "https://api.openreview.net"
    HEADERS = {"User-Agent": "ScholarLint/5.3 (mailto:integrity@check.org)"}
    MAX_CONCURRENT = 10
    TIMEOUT = 6.0

    def __init__(self):
        # Per-instance caches: prevent cross-paper cache pollution when multiple
        # papers are verified in the same process (e.g., run_demo.py loops).
        self._doi_cache: dict[str, tuple[dict | None, str]] = {}
        self._title_cache: dict[str, dict | None] = {}

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []
        verified_entries: list[dict] = []

        if not paper.bib_entries:
            return CheckResult(
                gate_name=self.name,
                gate_description=self.description,
                passed=False,
                score=0.0,
                issues=[Issue(
                    severity=Severity.ERROR,
                    message="No bibliography entries found",
                    suggestion="Ensure the .bib file contains valid bibliography entries",
                )],
                summary="No references to verify",
                metadata={},
            )

        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT)

        async with httpx.AsyncClient() as client:
            tasks = [
                self._verify_entry(entry, client, semaphore)
                for entry in paper.bib_entries
            ]
            results = await asyncio.gather(*tasks)

        total_pass = 0
        total_fail = 0

        for entry, (entry_issues, entry_meta) in zip(paper.bib_entries, results):
            issues.extend(entry_issues)
            verified_entries.append(entry_meta)
            if any(i.severity == Severity.ERROR for i in entry_issues):
                total_fail += 1
            else:
                total_pass += 1

        # Self-citation ratio check
        self._check_self_citation_ratio(paper, issues)

        # GPT fake author pattern detection
        self._check_fake_author_patterns(paper.bib_entries, issues)

        # Venue quality analysis (for NLP submissions)
        self._check_venue_quality(paper.bib_entries, issues)

        # Citation freshness analysis
        self._check_citation_freshness(paper.bib_entries, verified_entries, issues)

        total = len(paper.bib_entries)
        score = (total_pass / total * 100) if total > 0 else 0
        passed = total_fail == 0

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=f"{total} references: {total_pass} verified ✓, {total_fail} failed ✗",
            metadata={"verified_entries": verified_entries},
        )

    async def _resolve_doi(
        self, doi: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
    ) -> tuple[dict | None, str]:
        """尝试通过 Crossref 解析 DOI，失败则尝试 DataCite，再失败尝试 Semantic Scholar。

        Returns: (metadata_dict, source) where source is 'crossref'/'datacite'/'s2'/'none'
        """
        cache_key = doi.lower().strip()
        if cache_key in self._doi_cache:
            return self._doi_cache[cache_key]

        transient_failure = False

        async with semaphore:
            # Try Crossref first
            try:
                resp = await client.get(
                    f"{self.CROSSREF_BASE}/works/{doi}",
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    result = (resp.json().get("message", {}), "crossref")
                    self._doi_cache[cache_key] = result
                    return result
                if resp.status_code == 429 or resp.status_code >= 500:
                    transient_failure = True
            except (httpx.TimeoutException, httpx.HTTPError):
                transient_failure = True

            # Fallback to DataCite (handles arXiv, Zenodo, etc.)
            try:
                resp = await client.get(
                    f"{self.DATACITE_BASE}/dois/{doi}",
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    result = (resp.json().get("data", {}).get("attributes", {}), "datacite")
                    self._doi_cache[cache_key] = result
                    return result
                if resp.status_code == 429 or resp.status_code >= 500:
                    transient_failure = True
            except (httpx.TimeoutException, httpx.HTTPError):
                transient_failure = True

            # Fallback to Semantic Scholar
            try:
                resp = await client.get(
                    f"{self.S2_BASE}/paper/DOI:{doi}",
                    params={"fields": "title,authors,year,venue,externalIds"},
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    result = (resp.json(), "s2")
                    self._doi_cache[cache_key] = result
                    return result
                if resp.status_code == 429 or resp.status_code >= 500:
                    transient_failure = True
            except (httpx.TimeoutException, httpx.HTTPError):
                transient_failure = True

        result = (None, "unavailable" if transient_failure else "none")
        self._doi_cache[cache_key] = result
        return result

    def _extract_metadata(self, data: dict, source: str) -> tuple[str, list[dict], str]:
        """从 Crossref 或 DataCite 的响应中统一提取 title, authors, venue。"""
        if source == "crossref":
            titles = data.get("title") or []
            title = titles[0] if titles else ""
            authors = data.get("author", [])
            container = data.get("container-title") or []
            venue = container[0] if container else (data.get("event", {}).get("name", "") or "")
            return title, authors, venue
        elif source == "datacite":
            titles = data.get("titles", [])
            title = titles[0].get("title", "") if titles else ""
            creators = data.get("creators", [])
            # Convert DataCite authors to Crossref-like format
            authors = []
            for c in creators:
                name = c.get("name", "")
                if "," in name:
                    parts = name.split(",", 1)
                    authors.append({"family": parts[0].strip(), "given": parts[1].strip()})
                else:
                    name_parts = name.split()
                    if len(name_parts) >= 2:
                        authors.append({"family": name_parts[-1], "given": " ".join(name_parts[:-1])})
                    else:
                        authors.append({"family": name, "given": ""})
            # DataCite container
            container = data.get("container", {})
            venue = container.get("title", "") if container else ""
            return title, authors, venue
        elif source == "s2":
            # Semantic Scholar format
            title = data.get("title", "")
            s2_authors = data.get("authors", [])
            authors = []
            for a in s2_authors:
                name = a.get("name", "")
                parts = name.split()
                if len(parts) >= 2:
                    authors.append({"family": parts[-1], "given": " ".join(parts[:-1])})
                else:
                    authors.append({"family": name, "given": ""})
            venue = data.get("venue", "")
            return title, authors, venue
        return "", [], ""

    async def _verify_entry(
        self, entry: BibEntry, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
    ) -> tuple[list[Issue], dict]:
        """验证单条引文。返回 (issues, metadata_dict)。"""
        issues: list[Issue] = []
        location = f"bib:{entry.key}"
        # For editor integration: file and line of this bib entry
        issue_file = entry.source_file
        issue_line = entry.source_line

        meta = {
            "key": entry.key,
            "bib_title": entry.title or "",
            "bib_authors": entry.authors,
            "bib_venue": entry.journal or entry.booktitle or "",
            "doi": entry.doi,
            "doi_link": None,
            "crossref_title": None,
            "crossref_authors": None,
            "crossref_venue": None,
            "title_match": False,
            "authors_match": False,
            "venue_match": False,
            "source": None,
            "status": "unverified",
            "year": None,
        }

        # Step 1: DOI 检查
        # 可信来源 URL（即使没有 DOI 也可接受）
        trusted_url_patterns = [
            "arxiv.org", "proceedings.neurips.cc", "proceedings.mlr.press",
            "openreview.net", "aclanthology.org", "proceedings.iclr.cc",
            "dl.acm.org", "ieeexplore.ieee.org", "link.springer.com",
        ]
        entry_url = entry.url or entry.raw_fields.get("url", "")

        if not entry.doi:
            has_trusted_url = any(pat in entry_url for pat in trusted_url_patterns)
            if has_trusted_url:
                # Has a trusted source URL — downgrade to warning
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"[{entry.key}] Missing DOI (trusted source URL present)",
                    location=location, file=issue_file, line=issue_line,
                    evidence=f"URL: {entry_url}",
                    suggestion="Adding a DOI would enable automatic verification. The source is currently confirmed via URL.",
                ))
                meta["status"] = "no_doi_but_url"
                meta["doi_link"] = entry_url
                return issues, meta
            else:
                # No DOI and no trusted URL — attempt title-search verification
                if entry.title:
                    found = await self._search_by_title(entry.title, client, semaphore)
                    if found:
                        meta["status"] = "verified_by_title_search"
                        meta["doi_link"] = found.get("url", "")
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message=f"[{entry.key}] Missing DOI, but paper confirmed via title search",
                            location=location, file=issue_file, line=issue_line,
                            evidence=f"Title match: {found.get('title', '')[:80]}",
                            suggestion=f"Adding a DOI would enable precise verification. Found record: {found.get('url', '')}",
                        ))
                        return issues, meta

                # Title search also failed — check if this is a tech report, downgrade to WARNING
                raw_fields_text = " ".join(str(v) for v in entry.raw_fields.values())
                is_tech_report = (
                    _TECH_REPORT_KEY_RE.search(entry.key)
                    or _TECH_REPORT_FIELDS.search(raw_fields_text)
                    or entry.entry_type in ("misc", "online", "software")
                    and _TECH_REPORT_KEY_RE.search(entry.title or "")
                )
                if is_tech_report:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message=f"[{entry.key}] Technical report / model card lacks a DOI (cannot be automatically verified)",
                        location=location, file=issue_file, line=issue_line,
                        evidence=f"Title: {entry.title or 'N/A'}",
                        suggestion="Technical reports and model cards typically have no formal DOI. Consider adding an official URL in the note/url field for reader reference.",
                    ))
                    meta["status"] = "tech_report_no_doi"
                    return issues, meta

                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"[{entry.key}] Missing DOI, no trusted source, and title search returned no match",
                    location=location, file=issue_file, line=issue_line,
                    evidence=f"Title: {entry.title or 'N/A'}",
                    suggestion="Add a valid DOI (searchable at https://search.crossref.org/), or provide a URL from a trusted source such as arXiv, ACL Anthology, or NeurIPS.",
                ))
                meta["status"] = "no_doi"
                return issues, meta

        # Clean DOI
        doi = entry.doi.strip()
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
        meta["doi"] = doi
        meta["doi_link"] = f"https://doi.org/{doi}"

        # DOI format validation (must match 10.XXXX/... pattern)
        if not re.match(r"^10\.\d{4,9}/\S+$", doi):
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"[{entry.key}] Invalid DOI format: {doi}",
                location=location, file=issue_file, line=issue_line,
                evidence="A valid DOI must match the pattern 10.XXXX/... (e.g. 10.1145/3491102.3517582)",
                suggestion="Check that the DOI was entered correctly. A valid DOI begins with '10.'",
            ))
            meta["status"] = "doi_invalid_format"
            return issues, meta

        # Step 2: 解析 DOI（先 Crossref，后 DataCite）
        data, source = await self._resolve_doi(doi, client, semaphore)
        meta["source"] = source

        if data is None:
            if source == "unavailable":
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"[{entry.key}] DOI temporarily unverifiable: {doi}",
                    location=location, file=issue_file, line=issue_line,
                    evidence="Crossref/DataCite/Semantic Scholar is temporarily unavailable or rate-limiting. This reference is not being classified as fabricated.",
                    suggestion="Re-run the check later, or manually open the DOI link to verify the source.",
                ))
                meta["status"] = "verification_unavailable"
                return issues, meta
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"[{entry.key}] DOI cannot be resolved: {doi}",
                location=location, file=issue_file, line=issue_line,
                evidence="This DOI was not found in either Crossref or DataCite",
                suggestion=f"Confirm the DOI is correct. Verification link: https://doi.org/{doi}",
            ))
            meta["status"] = "doi_invalid"
            return issues, meta

        # Step 3: 提取元数据
        cr_title, cr_authors, cr_venue = self._extract_metadata(data, source)

        meta["crossref_title"] = cr_title
        meta["crossref_authors"] = [
            f"{a.get('given', '')} {a.get('family', '')}".strip() for a in cr_authors
        ]
        meta["crossref_venue"] = cr_venue

        # Step 3.5: Retraction detection
        if source == "crossref":
            # Check for retraction notices via "update-to" field
            updates = data.get("update-to", [])
            for upd in updates:
                if upd.get("type") == "retraction" or upd.get("label", "").lower() == "retraction":
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"[{entry.key}] ⚠️ This paper has been retracted (RETRACTED)",
                        location=location, file=issue_file, line=issue_line,
                        evidence=f"Title: {cr_title}\nDOI: {doi}",
                        suggestion=f"Citing a retracted paper is a serious issue. Remove this citation or justify its inclusion.\n🔗 https://doi.org/{doi}",
                    ))
                    meta["retracted"] = True
                    break
            # Also check "relation.is-retracted-by"
            relations = data.get("relation", {})
            if relations.get("is-retracted-by"):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"[{entry.key}] ⚠️ This paper has been retracted (RETRACTED)",
                    location=location, file=issue_file, line=issue_line,
                    evidence=f"Title: {cr_title}\nDOI: {doi}",
                    suggestion=f"Citing a retracted paper is a serious issue. Remove this citation or justify its inclusion.\n🔗 https://doi.org/{doi}",
                ))
                meta["retracted"] = True

        # Step 4: 标题验证（严格 — 标准化后必须 100% 一致）
        bib_title_norm = _normalize_title(entry.title or "")
        cr_title_norm = _normalize_title(cr_title)

        if bib_title_norm and cr_title_norm:
            if _title_matches(bib_title_norm, cr_title_norm):
                meta["title_match"] = True
            else:
                sim = SequenceMatcher(None, bib_title_norm, cr_title_norm).ratio()
                severity = Severity.WARNING if sim >= 0.60 else Severity.ERROR
                meta["title_match"] = False
                issues.append(Issue(
                    severity=severity,
                    message=f"[{entry.key}] Title mismatch (similarity {sim:.0%})",
                    location=location, file=issue_file, line=issue_line,
                    evidence=f"bib title: {entry.title}\nDatabase title: {cr_title}",
                    suggestion=f"Please correct the title in your .bib file to match the database record.\n🔗 Database source: https://doi.org/{doi}",
                ))
        elif bib_title_norm and not cr_title_norm:
            meta["title_match"] = True
            issues.append(Issue(
                severity=Severity.INFO,
                message=f"[{entry.key}] Database has no title metadata; title cannot be verified",
                location=location, file=issue_file, line=issue_line,
            ))
        elif not entry.title:
            issues.append(Issue(
                severity=Severity.ERROR,
                message=f"[{entry.key}] bib entry is missing the title field",
                location=location, file=issue_file, line=issue_line,
                suggestion="Every bibliography entry must include a title field.",
            ))

        # Step 5: 作者验证（严格 — 姓氏必须逐位对应）
        if entry.authors and cr_authors:
            bib_families = [_extract_family_name(a) for a in entry.authors]
            cr_families_direct = [a.get("family", "").lower().strip() for a in cr_authors]
            cr_fam = cr_families_direct if any(cr_families_direct) else [
                _extract_family_name(f"{a.get('given', '')} {a.get('family', '')}")
                for a in cr_authors
            ]

            if len(bib_families) != len(cr_fam):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"[{entry.key}] Author count mismatch: .bib has {len(bib_families)}, database has {len(cr_fam)}",
                    location=location, file=issue_file, line=issue_line,
                    evidence=(
                        f"bib ({len(entry.authors)} author(s)): {', '.join(entry.authors)}\n"
                        f"Database ({len(cr_fam)} author(s)): {', '.join(meta['crossref_authors'])}"
                    ),
                    suggestion=f"The author count does not match the database record. Check for missing or extra authors.\n🔗 Database source: https://doi.org/{doi}",
                ))
            else:
                mismatches = []
                for i, (bib_f, cr_f) in enumerate(zip(bib_families, cr_fam)):
                    if not bib_f or not cr_f:
                        continue
                    if bib_f != cr_f:
                        fam_sim = SequenceMatcher(None, bib_f, cr_f).ratio()
                        if fam_sim < 0.90:
                            mismatches.append((
                                entry.authors[i],
                                meta["crossref_authors"][i] if i < len(meta["crossref_authors"]) else "?",
                                bib_f, cr_f,
                            ))

                if mismatches:
                    meta["authors_match"] = False
                    evidence_lines = [
                        f"  Author {i+1}: bib '{m[0]}' (family: '{m[2]}') ≠ database '{m[1]}' (family: '{m[3]}')"
                        for i, m in enumerate(mismatches)
                    ]
                    doi_url = f"https://doi.org/{doi}" if doi else ""
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"[{entry.key}] Author surname mismatch ({len(mismatches)} discrepancy/discrepancies)",
                        location=location, file=issue_file, line=issue_line,
                        evidence="\n".join(evidence_lines),
                        suggestion=f"Author surnames do not match the database record. Please verify and correct them.\n🔗 Database source: {doi_url}" if doi_url else "Author surnames do not match the database record. Please verify and correct them.",
                    ))
                else:
                    meta["authors_match"] = True
        elif entry.authors and not cr_authors:
            meta["authors_match"] = True
            issues.append(Issue(
                severity=Severity.INFO,
                message=f"[{entry.key}] Database has no author metadata; authors cannot be verified",
                location=location, file=issue_file, line=issue_line,
            ))
        elif not entry.authors:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"[{entry.key}] bib entry is missing the author field",
                location=location, file=issue_file, line=issue_line,
                suggestion="Please add an author field to the bib entry.",
            ))

        # Step 6: 期刊/会议验证（宽松 — 缩写、全称、年份差异很常见）
        bib_venue = entry.journal or entry.booktitle or ""
        if bib_venue and cr_venue:
            bib_venue_norm = _normalize_title(bib_venue)
            cr_venue_norm = _normalize_title(cr_venue)
            venue_sim = SequenceMatcher(None, bib_venue_norm, cr_venue_norm).ratio()
            # 包含关系（缩写 vs 全称）
            contains = bib_venue_norm in cr_venue_norm or cr_venue_norm in bib_venue_norm
            # 关键词重叠（去通用词）
            stop_words = {'proceedings', 'of', 'the', 'on', 'in', 'conference', 'journal', 'international', 'annual', 'workshop', 'symposium'}
            bib_kw = set(bib_venue_norm.split()) - stop_words
            cr_kw = set(cr_venue_norm.split()) - stop_words
            kw_overlap = len(bib_kw & cr_kw) / max(len(bib_kw), 1) if bib_kw else 0

            meta["venue_match"] = venue_sim >= 0.50 or contains or kw_overlap >= 0.3

            if not meta["venue_match"]:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"[{entry.key}] Venue name mismatch (similarity {venue_sim:.0%})",
                    location=location, file=issue_file, line=issue_line,
                    evidence=f"bib: {bib_venue}\nDatabase: {cr_venue}",
                    suggestion=f"The venue name differs from the database record. Check for spelling errors or incorrect abbreviations.\n🔗 Database source: https://doi.org/{doi}",
                ))
        elif bib_venue and not cr_venue:
            meta["venue_match"] = True  # Database has no venue data

        # Step 7: Official citation format check (ACL/DBLP)
        official_bib_url = self._get_official_bib_url(doi)
        meta["official_bib_url"] = official_bib_url
        if official_bib_url and not meta.get("venue_match"):
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"[{entry.key}] Consider using the official citation format",
                location=location, file=issue_file, line=issue_line,
                evidence=f"Official bib URL: {official_bib_url}",
                suggestion=f"Obtain a standard bib entry from the official source to avoid formatting discrepancies. Link: {official_bib_url}",
            ))
        elif official_bib_url:
            meta["official_bib_url"] = official_bib_url

        # Step 8: 年份一致性检查
        if entry.year and data:
            db_year = None
            if source == "crossref":
                issued = data.get("issued", {}).get("date-parts", [[]])
                if issued and issued[0]:
                    db_year = str(issued[0][0])
            elif source == "datacite":
                db_year = str(data.get("publicationYear", ""))

            if db_year and entry.year.strip() != db_year:
                try:
                    diff = abs(int(entry.year.strip()) - int(db_year))
                except ValueError:
                    diff = 0
                if diff > 1:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message=f"[{entry.key}] Year mismatch: .bib has {entry.year}, database has {db_year}",
                        location=location, file=issue_file, line=issue_line,
                        evidence=f"Difference: {diff} year(s)",
                        suggestion=f"Check whether the year is correct. The database record shows {db_year}.\n🔗 https://doi.org/{doi}",
                    ))
                elif diff == 1:
                    # 1 year diff is common (preprint vs published), just info
                    pass

        # Set year in metadata for analysis
        if entry.year:
            try:
                meta["year"] = int(entry.year.strip())
            except (ValueError, TypeError):
                pass

        # 5-level classification (matching GPTZero's taxonomy)
        has_errors = any(i.severity == Severity.ERROR for i in issues)
        has_warnings = any(i.severity == Severity.WARNING for i in issues)

        if has_errors:
            # Check if it's truly fake or just unverifiable
            error_msgs = " ".join(i.message for i in issues if i.severity == Severity.ERROR)
            if "mismatch" in error_msgs or "cannot be resolved" in error_msgs:
                meta["status"] = "fake"  # Fabricated or unmatched
            else:
                meta["status"] = "unsure"  # Cannot determine
        elif has_warnings:
            meta["status"] = "minor_issues"  # Real but with discrepancies
        elif meta.get("source") is None and not entry.doi:
            meta["status"] = "unknown"  # Cannot verify (no DOI, no source found)
        else:
            meta["status"] = "pass"  # Verified real source

        return issues, meta

    @staticmethod
    def _get_official_bib_url(doi: str) -> str | None:
        """根据 DOI 前缀判断来源，返回官方 BIB 下载链接。"""
        if not doi:
            return None

        # ACL Anthology: DOI prefix 10.18653/v1/
        if doi.startswith("10.18653/v1/"):
            acl_id = doi.split("/")[-1]
            return f"https://aclanthology.org/{acl_id}.bib"

        # EMNLP/ACL newer format: 10.18653/v1/2025.emnlp-main.300
        if doi.startswith("10.18653/"):
            parts = doi.replace("10.18653/v1/", "").replace("10.18653/", "")
            return f"https://aclanthology.org/{parts}.bib"

        # ACM: DOI prefix 10.1145/
        if doi.startswith("10.1145/"):
            return f"https://dl.acm.org/doi/{doi}#sec-cite-as"

        # IEEE: DOI prefix 10.1109/
        if doi.startswith("10.1109/"):
            return f"https://dblp.org/doi/{doi}.bib"

        # Springer/Nature: 10.1007/
        if doi.startswith("10.1007/"):
            return f"https://dblp.org/doi/{doi}.bib"

        # DBLP as universal fallback for CS papers
        # Try DBLP for any DOI (it covers most CS venues)
        return f"https://dblp.org/doi/{doi}.bib"

    async def _search_by_title(
        self, title: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore
    ) -> dict | None:
        """Search for a paper by title in Crossref and Semantic Scholar.

        Returns dict with 'title' and 'url' if found with high confidence, else None.
        """
        norm_title = _normalize_title(title)
        if not norm_title or len(norm_title) < 10:
            return None
        if norm_title in self._title_cache:
            return self._title_cache[norm_title]

        async with semaphore:
            # Try Crossref title search
            try:
                resp = await client.get(
                    f"{self.CROSSREF_BASE}/works",
                    params={"query.title": title, "rows": 3},
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    items = resp.json().get("message", {}).get("items", [])
                    for item in items:
                        item_titles = item.get("title", [])
                        if item_titles:
                            item_norm = _normalize_title(item_titles[0])
                            if _title_matches(item_norm, norm_title):
                                doi = item.get("DOI", "")
                                result = {"title": item_titles[0], "url": f"https://doi.org/{doi}" if doi else ""}
                                self._title_cache[norm_title] = result
                                return result
            except (httpx.TimeoutException, httpx.HTTPError):
                pass

            # Try Semantic Scholar title search
            try:
                resp = await client.get(
                    f"{self.S2_BASE}/paper/search",
                    params={"query": title, "limit": 3, "fields": "title,externalIds"},
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    papers = resp.json().get("data", [])
                    for paper in papers:
                        paper_title = paper.get("title", "")
                        if _title_matches(_normalize_title(paper_title), norm_title):
                            ext_ids = paper.get("externalIds", {})
                            doi = ext_ids.get("DOI", "")
                            url = f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}"
                            result = {"title": paper_title, "url": url}
                            self._title_cache[norm_title] = result
                            return result
            except (httpx.TimeoutException, httpx.HTTPError):
                pass

            # Try OpenReview (ICLR, NeurIPS, ICML workshops, COLM, etc.)
            try:
                resp = await client.get(
                    f"{self.OPENREVIEW_BASE}/notes/search",
                    params={"term": title, "limit": 3, "source": "forum", "offset": 0},
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    notes = resp.json().get("notes", [])
                    for note in notes:
                        note_title = note.get("content", {}).get("title", "")
                        if isinstance(note_title, dict):
                            note_title = note_title.get("value", "")
                        if note_title and _title_matches(_normalize_title(note_title), norm_title):
                            forum_id = note.get("forum", note.get("id", ""))
                            url = f"https://openreview.net/forum?id={forum_id}" if forum_id else "https://openreview.net"
                            result = {"title": note_title, "url": url}
                            self._title_cache[norm_title] = result
                            return result
            except (httpx.TimeoutException, httpx.HTTPError):
                pass

            # Try OpenAlex title search
            try:
                resp = await client.get(
                    f"{self.OPENALEX_BASE}/works",
                    params={"filter": f"title.search:{title}", "per_page": 3},
                    headers=self.HEADERS,
                    timeout=self.TIMEOUT,
                )
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    for work in results:
                        work_title = work.get("title", "")
                        if _title_matches(_normalize_title(work_title), norm_title):
                            doi = work.get("doi", "")
                            url = doi if doi else work.get("id", "")
                            result = {"title": work_title, "url": url}
                            self._title_cache[norm_title] = result
                            return result
            except (httpx.TimeoutException, httpx.HTTPError):
                pass

        self._title_cache[norm_title] = None
        return None

    @staticmethod
    def _check_self_citation_ratio(paper, issues: list):
        """Check if self-citation ratio is suspiciously high (>30%)."""
        if not paper.bib_entries or not paper.tex_files:
            return

        # Extract author names from the paper's \author{} block
        paper_authors = set()
        for tex_file in paper.tex_files:
            if not tex_file.is_main:
                continue
            # Find \author{...} block
            author_match = re.search(r"\\author\{(.*?)\}", tex_file.raw_text, re.DOTALL)
            if author_match:
                author_text = author_match.group(1)
                # Extract family names (heuristic: words that look like names)
                # Remove LaTeX commands and affiliation markers
                author_text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", author_text)
                author_text = re.sub(r"\\[a-zA-Z]+", "", author_text)
                author_text = author_text.replace("{", "").replace("}", "")
                # Split by common delimiters (\\, \and, commas between name groups)
                names = re.split(r"\\\\|\\and|,\s*(?=[A-Z])", author_text)
                for name in names:
                    name = name.strip()
                    if name:
                        # Take last word as family name
                        parts = name.split()
                        if parts:
                            family = parts[-1].lower().strip(".,;")
                            if len(family) > 1:
                                paper_authors.add(family)

        if not paper_authors:
            return

        # Count self-citations
        self_cite_count = 0
        for entry in paper.bib_entries:
            for author in entry.authors:
                family = _extract_family_name(author)
                if family in paper_authors:
                    self_cite_count += 1
                    break

        total = len(paper.bib_entries)
        if total < 5:
            return

        ratio = self_cite_count / total
        if ratio > 0.30:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"High self-citation ratio: {self_cite_count}/{total} ({ratio:.0%}) of references include an author of this paper",
                location="global",
                evidence=f"Author surnames in this paper: {', '.join(sorted(paper_authors)[:5])}",
                suggestion="A self-citation ratio above 30% may raise concerns among reviewers. Check whether all self-citations are necessary.",
            ))

    @staticmethod
    def _check_fake_author_patterns(bib_entries, issues: list):
        """Detect patterns typical of GPT-fabricated author names."""
        # Top-20 most common English surnames (GPT tends to use these for fake names)
        COMMON_SURNAMES = {
            "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
            "davis", "rodriguez", "martinez", "hernandez", "lopez", "gonzalez",
            "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
            "lee", "wang", "zhang", "li", "chen", "liu", "yang",
        }

        suspicious_entries = []
        for entry in bib_entries:
            if len(entry.authors) < 3:
                continue
            families = [_extract_family_name(a) for a in entry.authors]
            common_count = sum(1 for f in families if f in COMMON_SURNAMES)
            if common_count == len(families):
                suspicious_entries.append(entry)

        if suspicious_entries:
            for entry in suspicious_entries[:3]:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"[{entry.key}] All author surnames are very common names (possible GPT fabrication)",
                    location=f"bib:{entry.key}",
                    file=entry.source_file,
                    line=entry.source_line,
                    evidence=f"Authors: {', '.join(entry.authors[:5])}",
                    suggestion="All author surnames appear in the top-20 most common surname list, a pattern typical of GPT-fabricated references. Please verify that this paper actually exists.",
                ))


    @staticmethod
    def _check_venue_quality(bib_entries, issues: list):
        """Check if references include enough papers from top venues in the target field."""
        # NLP top venues
        NLP_VENUES = {
            "acl", "emnlp", "naacl", "eacl", "coling", "tacl",
            "computational linguistics", "findings of acl", "findings of emnlp",
            "proceedings of the association for computational linguistics",
            "proceedings of the.*conference on empirical methods",
            "proceedings of the.*north american chapter",
            "transactions of the association for computational linguistics",
        }
        # ML/AI top venues
        ML_VENUES = {
            "neurips", "nips", "icml", "iclr", "aaai", "ijcai",
            "journal of machine learning research", "jmlr",
        }

        if not bib_entries or len(bib_entries) < 5:
            return

        # Count venue matches
        nlp_count = 0
        ml_count = 0
        for entry in bib_entries:
            venue = (entry.journal or entry.booktitle or "").lower()
            # Check NLP venues
            for v in NLP_VENUES:
                if v in venue or re.search(v, venue):
                    nlp_count += 1
                    break
            # Check ML venues
            for v in ML_VENUES:
                if v in venue:
                    ml_count += 1
                    break

        total = len(bib_entries)
        top_venue_ratio = (nlp_count + ml_count) / total

        # If very few NLP venues cited, warn (likely targeting NLP conference)
        if nlp_count <= 2 and total >= 10:
            issues.append(Issue(
                severity=Severity.INFO,
                message=f"Few top NLP venue citations: only {nlp_count}/{total} from ACL/EMNLP/NAACL/TACL",
                location="global",
                evidence=f"NLP venue: {nlp_count}, ML venue: {ml_count}, Other: {total - nlp_count - ml_count}",
                suggestion="If submitting to an NLP venue (ACL/EMNLP/NAACL), consider citing more recent papers from those venues to demonstrate awareness of the field.",
            ))

        # If mostly citing non-top venues
        if top_venue_ratio < 0.2 and total >= 15:
            issues.append(Issue(
                severity=Severity.INFO,
                message=f"Low top-venue citation ratio: {nlp_count+ml_count}/{total} ({top_venue_ratio:.0%})",
                location="global",
                suggestion="Consider adding citations from top venues such as ACL/EMNLP/NeurIPS/ICML to strengthen the paper's positioning.",
            ))

    @staticmethod
    def _check_citation_freshness(
        bib_entries: list, verified_entries: list[dict], issues: list
    ):
        """Check if citations are too old — reviewers care about recency."""
        from datetime import datetime

        current_year = datetime.now().year
        years = []

        for entry in bib_entries:
            year = entry.year or entry.raw_fields.get("year")
            if year:
                try:
                    y = int(year.strip())
                    if 1900 < y <= current_year:
                        years.append(y)
                except (ValueError, TypeError):
                    pass

        # Also extract years from verified_entries metadata
        for ve in verified_entries:
            y = ve.get("year")
            if y and isinstance(y, int) and 1900 < y <= current_year:
                if y not in years:
                    years.append(y)

        if len(years) < 5:
            return  # Not enough data to judge

        years.sort()
        median_year = years[len(years) // 2]
        recent_count = sum(1 for y in years if y >= current_year - 3)
        recent_pct = recent_count / len(years) * 100
        old_count = sum(1 for y in years if y < current_year - 10)
        old_pct = old_count / len(years) * 100

        # Warning: median year is very old
        if median_year < current_year - 8:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"Citations are generally old: median publication year is {median_year} ({current_year - median_year} years ago)",
                location="global",
                suggestion=f"The median publication year of your references is {median_year}. "
                f"A large proportion of old references may lead reviewers to question your familiarity with recent advances. "
                f"Consider adding relevant work from {current_year-2}–{current_year}.",
            ))

        # Warning: very few recent papers
        if recent_pct < 15 and len(years) >= 10:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"Low proportion of recent citations: {recent_count}/{len(years)} ({recent_pct:.0f}%) from the past 3 years",
                location="global",
                suggestion=f"Only {recent_pct:.0f}% of your references were published in {current_year-3}–{current_year}. "
                f"Reviewers may conclude that you have not sufficiently surveyed recent work. "
                f"Aim for at least 25–30% of citations from the past 3 years.",
            ))

        # Warning: too many very old papers (>10 years)
        if old_pct > 50 and len(years) >= 10:
            issues.append(Issue(
                severity=Severity.WARNING,
                message=f"More than half of the references are over 10 years old: {old_count}/{len(years)} ({old_pct:.0f}%)",
                location="global",
                suggestion="Over half of your cited works are more than 10 years old. "
                "While seminal papers deserve citation, an excess of old references may be seen by reviewers as insufficient coverage of related work.",
            ))

        # Store year info in verified_entries for frontend display
        # (already available via the analysis API endpoint)
