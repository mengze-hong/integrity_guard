"""Parse hallucinated citation entries from ICLR desk-reject reasons,
then verify each against Crossref + arXiv to classify the fabrication type.

Input:  research/bench/iclr_desk_rejected.json  (649 fabricated_reference cases)
Output: research/bench/hallucinated_citations_verified.json

Classification per citation:
  truly_nonexistent   — title search in Crossref + arXiv finds nothing close
  arxiv_id_wrong      — arXiv ID exists but points to a different paper
  metadata_mismatch   — paper exists but title/author/venue info is wrong
  unverifiable        — not enough info to check (abbreviated authors, etc.)
"""
import httpx, json, re, time
from pathlib import Path
from collections import Counter

OUT = Path(__file__).parent / "hallucinated_citations_verified.json"
DATA = Path(__file__).parent / "iclr_desk_rejected.json"
MAILTO = "ops@scholarlint.example"


# ── citation parser ────────────────────────────────────────────────────────────

ARXIV_RE = re.compile(r"arXiv(?:\s*preprint)?\s*arXiv[:\s]+(\d{4}\.\d{4,5})", re.I)
DOI_RE   = re.compile(r"10\.\d{4,9}/\S+")

def parse_citations(reason: str) -> list[dict]:
    """Split a rejection reason into individual citation entries."""
    # The PC text starts with a header, then one citation per paragraph/line-group
    # Strip the standard header
    text = re.sub(
        r"The following references[^\n]*\n?|"
        r"Desk rejected[^\n]*\n?|"
        r"Hallucinated reference[:\s]*",
        "", reason, flags=re.I
    ).strip()

    # Split on blank lines or lines that look like new citation starts
    # (capital letter, likely author name)
    raw_entries = re.split(r"\n{2,}|\n(?=[A-Z][a-z]|\d+\.)", text)

    citations = []
    for raw in raw_entries:
        raw = raw.strip()
        if len(raw) < 20:
            continue

        arxiv_ids = ARXIV_RE.findall(raw)
        dois      = DOI_RE.findall(raw)

        # Extract title: usually after first period that ends author block,
        # or quoted, or the whole first sentence
        title = ""
        # Try: "Authors. Title. Venue" pattern
        m = re.match(r"^[^.]{10,120}\.\s+(.+?)(?:\.\s+(?:In |arXiv|IEEE|ACM|Proc|Journal|Workshop|\d{4})|\.$)", raw)
        if m:
            title = m.group(1).strip()
        if not title:
            # fallback: second sentence
            sents = re.split(r"\.\s+", raw)
            if len(sents) >= 2:
                title = sents[1].strip()[:150]

        # Extract year
        year_m = re.search(r"\b(20\d{2})\b", raw)
        year = year_m.group(1) if year_m else ""

        citations.append({
            "raw": raw[:400],
            "title": title[:150],
            "year": year,
            "arxiv_ids": arxiv_ids,
            "dois": dois,
            "verified": False,
            "classification": "unverified",
            "verification_detail": "",
        })
    return citations


# ── verification ───────────────────────────────────────────────────────────────

def verify_arxiv(arxiv_id: str, expected_title: str, client: httpx.Client) -> tuple[str, str]:
    """Check if arXiv ID exists and if the title matches."""
    try:
        r = client.get(
            "http://export.arxiv.org/api/query",
            params={"id_list": arxiv_id, "max_results": 1}, timeout=15)
        if r.status_code != 200:
            return "unverifiable", f"arXiv API error {r.status_code}"
        text = r.text
        if "<entry>" not in text:
            return "truly_nonexistent", f"arXiv:{arxiv_id} not found in arXiv"
        # extract title from XML
        tm = re.search(r"<title>(.*?)</title>", text, re.S)
        real_title = tm.group(1).strip() if tm else ""
        if not expected_title or not real_title:
            return "arxiv_exists_unverified", f"arXiv:{arxiv_id} exists: {real_title[:80]}"
        # compare similarity
        from difflib import SequenceMatcher
        sim = SequenceMatcher(None, expected_title.lower(), real_title.lower()).ratio()
        if sim > 0.7:
            return "metadata_mismatch", f"arXiv:{arxiv_id} exists with similar title (sim={sim:.2f}): {real_title[:80]}"
        else:
            return "arxiv_id_wrong", f"arXiv:{arxiv_id} exists but different paper: {real_title[:80]}"
    except Exception as e:
        return "unverifiable", f"arXiv check error: {str(e)[:60]}"


def verify_crossref(title: str, client: httpx.Client) -> tuple[str, str]:
    """Search Crossref by title; check if anything close exists."""
    if not title or len(title) < 15:
        return "unverifiable", "title too short"
    try:
        r = client.get(
            "https://api.crossref.org/works",
            params={"query.title": title, "rows": 3,
                    "select": "DOI,title,score",
                    "mailto": MAILTO},
            timeout=20)
        if r.status_code != 200:
            return "unverifiable", f"Crossref error {r.status_code}"
        items = r.json()["message"]["items"]
        if not items:
            return "truly_nonexistent", "not found in Crossref title search"
        top = items[0]
        cr_title = (top.get("title") or [""])[0]
        from difflib import SequenceMatcher
        sim = SequenceMatcher(None, title.lower(), cr_title.lower()).ratio()
        if sim > 0.75:
            return "metadata_mismatch", f"similar title exists in Crossref (sim={sim:.2f}): {cr_title[:80]}"
        elif sim > 0.45:
            return "truly_nonexistent", f"best Crossref match sim={sim:.2f} ({cr_title[:60]}) — too low"
        else:
            return "truly_nonexistent", f"no close match in Crossref (best sim={sim:.2f})"
    except Exception as e:
        return "unverifiable", f"Crossref error: {str(e)[:60]}"


def verify_citation(cit: dict, client: httpx.Client) -> dict:
    c = cit.copy()

    # 1. If has arXiv ID, check arXiv first
    for arxiv_id in c.get("arxiv_ids", [])[:1]:
        cls, detail = verify_arxiv(arxiv_id, c["title"], client)
        c["verified"] = True
        c["classification"] = cls
        c["verification_detail"] = detail
        return c

    # 2. Title search in Crossref
    if c["title"] and len(c["title"]) > 15:
        cls, detail = verify_crossref(c["title"], client)
        c["verified"] = True
        c["classification"] = cls
        c["verification_detail"] = detail
        return c

    c["classification"] = "unverifiable"
    c["verification_detail"] = "no arXiv ID and no usable title"
    return c


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    records = json.loads(DATA.read_text(encoding="utf-8"))["records"]
    fab = [r for r in records if r["category"] == "fabricated_reference"
           and r["year"] in (2025, 2026)]
    print(f"Fabricated-reference cases (2025-2026): {len(fab)}")

    # Resume support
    done: dict[str, list] = {}
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        done = {e["paper_forum"]: e["citations"] for e in prev.get("entries", [])}
        print(f"Resuming: {len(done)} papers already done")

    entries = []
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for i, paper in enumerate(fab):
            fid = paper["forum"]
            if fid in done:
                entries.append({"paper_forum": fid, "paper_title": paper["title"],
                                 "year": paper["year"], "citations": done[fid]})
                continue

            reason = paper.get("rejection_reason", "")
            cits = parse_citations(reason)
            if not cits:
                continue

            verified_cits = []
            for cit in cits[:4]:  # max 4 citations per paper
                vc = verify_citation(cit, client)
                verified_cits.append(vc)
                time.sleep(0.3)

            entries.append({
                "paper_forum": fid,
                "paper_title": paper["title"],
                "year": paper["year"],
                "citations": verified_cits,
            })

            # save checkpoint
            if (i + 1) % 20 == 0:
                _save(entries)
                cls_so_far = Counter(c["classification"]
                                     for e in entries for c in e["citations"])
                print(f"  [{i+1}/{len(fab)}] {dict(cls_so_far.most_common())}")

            time.sleep(0.15)

    _save(entries)

    # Final stats
    all_cits = [c for e in entries for c in e["citations"]]
    cls_counts = Counter(c["classification"] for c in all_cits)
    print(f"\n=== DONE: {len(entries)} papers, {len(all_cits)} citations verified ===")
    print("Classification breakdown:")
    for k, v in cls_counts.most_common():
        print(f"  {k:30s}: {v:4d} ({v/len(all_cits)*100:.1f}%)")

    # Show examples of each class
    print("\n=== Sample per class ===")
    shown = set()
    for c in all_cits:
        cls = c["classification"]
        if cls not in shown:
            shown.add(cls)
            print(f"\n[{cls}]")
            print(f"  title: {c['title'][:80]}")
            print(f"  detail: {c['verification_detail'][:100]}")


def _save(entries):
    all_cits = [c for e in entries for c in e["citations"]]
    cls_counts = Counter(c["classification"] for c in all_cits)
    OUT.write_text(json.dumps({
        "meta": {"papers": len(entries), "citations": len(all_cits),
                 "classification_counts": dict(cls_counts)},
        "entries": entries,
    }, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
