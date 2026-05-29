"""Crossref API service - verify DOIs, authors, journals."""

import asyncio
from difflib import SequenceMatcher

import httpx

from app.config import settings


class CrossrefService:
    """Service for querying Crossref API to verify references."""

    def __init__(self):
        self.base_url = settings.crossref_base_url
        self.headers = {
            "User-Agent": f"ScholarLint/5.3 (mailto:{settings.crossref_email})",
        }
        self._semaphore = asyncio.Semaphore(settings.crossref_max_concurrent)

    async def verify_doi(self, doi: str, client: httpx.AsyncClient) -> dict | None:
        """Query Crossref for a DOI and return metadata.

        Returns None if DOI not found or invalid.
        """
        async with self._semaphore:
            url = f"{self.base_url}/works/{doi}"
            try:
                resp = await client.get(
                    url,
                    headers=self.headers,
                    timeout=settings.crossref_timeout,
                )
                if resp.status_code == 200:
                    return resp.json().get("message", {})
                return None
            except (httpx.TimeoutException, httpx.HTTPError):
                return None

    def compare_title(self, bib_title: str, crossref_title: str) -> float:
        """Compare titles and return similarity score (0-1)."""
        if not bib_title or not crossref_title:
            return 0.0
        # Normalize: lowercase, strip braces (LaTeX), extra spaces
        norm_bib = bib_title.lower().replace("{", "").replace("}", "").strip()
        norm_cr = crossref_title.lower().strip()
        return SequenceMatcher(None, norm_bib, norm_cr).ratio()

    def compare_authors(
        self, bib_authors: list[str], crossref_authors: list[dict]
    ) -> tuple[float, list[str]]:
        """Compare author lists. Returns (score, list of mismatched authors).

        crossref_authors format: [{"family": "Smith", "given": "John"}, ...]
        """
        if not bib_authors or not crossref_authors:
            return 0.0, []

        cr_names = []
        for a in crossref_authors:
            family = a.get("family", "")
            given = a.get("given", "")
            cr_names.append(f"{given} {family}".strip().lower())

        mismatches = []
        matched = 0

        for bib_author in bib_authors:
            bib_norm = bib_author.lower().strip()
            # Try to match against any crossref author
            best_score = 0.0
            for cr_name in cr_names:
                score = SequenceMatcher(None, bib_norm, cr_name).ratio()
                best_score = max(best_score, score)
                # Also try "Last, First" → "First Last" conversion
                if "," in bib_norm:
                    parts = bib_norm.split(",", 1)
                    flipped = f"{parts[1].strip()} {parts[0].strip()}"
                    score2 = SequenceMatcher(None, flipped, cr_name).ratio()
                    best_score = max(best_score, score2)

            if best_score >= 0.75:
                matched += 1
            else:
                mismatches.append(bib_author)

        score = matched / len(bib_authors) if bib_authors else 0.0
        return score, mismatches

    def extract_crossref_title(self, metadata: dict) -> str:
        """Extract title from Crossref metadata."""
        titles = metadata.get("title", [])
        return titles[0] if titles else ""

    def extract_crossref_authors(self, metadata: dict) -> list[dict]:
        """Extract authors from Crossref metadata."""
        return metadata.get("author", [])


# Singleton
crossref_service = CrossrefService()
