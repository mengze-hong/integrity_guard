"""Sample generator: real Crossref-backed reference test cases.

Pulls real papers (multi-domain) + a real retracted paper from Crossref,
constructs a handful of reference-authenticity cases across categories and
difficulty tiers, then runs ScholarLint's reference gate on each so we can
eyeball: the .bib entry, the injected error, the ground-truth label, and
what ScholarLint actually reports.

Run: python research/bench/gen_crossref_cases.py
Out: research/bench/crossref_cases_sample.json
"""

from __future__ import annotations
import asyncio
import json
import sys
import tempfile
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

MAILTO = "ops@scholarlint.example"
OUT = Path(__file__).parent / "crossref_cases_sample.json"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": f"ScholarLintBench/1.0 (mailto:{MAILTO})"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _query_one(topic: str, filt: str = "type:proceedings-article") -> dict | None:
    q = urllib.parse.quote(topic)
    url = (f"https://api.crossref.org/works?query.bibliographic={q}"
           f"&filter={filt}&rows=3"
           f"&select=DOI,title,author,published,container-title&mailto={MAILTO}")
    items = _get(url)["message"]["items"]
    for it in items:
        if it.get("title") and it.get("author") and len(it["author"]) >= 2:
            return it
    return items[0] if items else None


def _one_retracted() -> dict:
    url = (f"https://api.crossref.org/works?filter=update-type:retraction"
           f"&rows=5&select=DOI,title,author,published,container-title,update-to&mailto={MAILTO}")
    for it in _get(url)["message"]["items"]:
        if it.get("title") and it.get("author"):
            return it
    raise RuntimeError("no retracted sample")


def _authors(it: dict) -> list[str]:
    out = []
    for a in it.get("author", []):
        name = (a.get("given", "") + " " + a.get("family", "")).strip()
        if name:
            out.append(name)
    return out


def _year(it: dict) -> str:
    dp = it.get("published", {}).get("date-parts", [[None]])
    return str(dp[0][0]) if dp and dp[0] and dp[0][0] else "2020"


def _venue(it: dict) -> str:
    v = it.get("container-title") or [""]
    return v[0] if v else ""


def _bib(key: str, title: str, authors: list[str], year: str, doi: str, venue: str) -> str:
    return (f"@inproceedings{{{key},\n"
            f"  author = {{{' and '.join(authors)}}},\n"
            f"  title = {{{title}}},\n"
            f"  year = {{{year}}},\n"
            f"  doi = {{{doi}}},\n"
            f"  booktitle = {{{venue}}}\n}}")


async def _run_gate(bib: str) -> list[str]:
    from app.parsers.tex_parser import parse_all_tex_files
    from app.parsers.bib_parser import parse_all_bib_files
    from app.models import ParsedPaper
    from app.checks.gate_references import ReferenceAuthenticityGate
    d = Path(tempfile.mkdtemp())
    try:
        tex = (r"\documentclass{article}\begin{document}"
               r"We build on prior work \citep{ref1}." "\n"
               r"\bibliography{refs}\end{document}")
        (d / "main.tex").write_text(tex, encoding="utf-8")
        (d / "refs.bib").write_text(bib, encoding="utf-8")
        paper = ParsedPaper(
            project_dir=d,
            tex_files=parse_all_tex_files(list(d.glob("*.tex"))),
            bib_entries=parse_all_bib_files(list(d.glob("*.bib"))),
            all_files=list(d.iterdir()), figure_files=[])
        res = await ReferenceAuthenticityGate().check(paper)
        return [f"{i.severity.value.upper()}: {i.message}" for i in res.issues]
    finally:
        shutil.rmtree(d, ignore_errors=True)


async def main():
    print("Fetching real papers from Crossref (multi-domain)...")
    pA = _query_one("neural machine translation transformer")          # CS/NLP
    pB = _query_one("deep learning image classification convolutional")  # CS/CV
    pMed = _query_one("crispr gene editing cancer therapy", "type:journal-article")  # bio/med
    ret = _one_retracted()
    print(f"  A(CS)  : {pA['DOI']}  {(pA['title'][0])[:45]}")
    print(f"  B(CS)  : {pB['DOI']}  {(pB['title'][0])[:45]}")
    print(f"  Med    : {pMed['DOI']}  {(pMed['title'][0])[:45]}")
    print(f"  Retract: {ret['DOI']}  {(ret['title'][0])[:45]}")

    cases = []

    def add(cat, difficulty, needs_ext, note, bib):
        cases.append({"category": cat, "difficulty": difficulty,
                      "requires_external_verification": needs_ext,
                      "note": note, "bib": bib})

    # C1 CLEAN — real paper, correct metadata (should pass / no ERROR)
    add("clean", "-", False, "real paper, correct metadata",
        _bib("ref1", pA["title"][0], _authors(pA), _year(pA), pA["DOI"], _venue(pA)))

    # C2 RETRACTED — cite a genuinely retracted paper (LLM can't know)
    add("cites_retracted", "hard", True, "real retracted paper; only Crossref knows",
        _bib("ref1", ret["title"][0].replace("RETRACTED:", "").replace("WITHDRAWN:", "").strip(),
             _authors(ret), _year(ret), ret["DOI"], _venue(ret)))

    # C3 DOI SWAP — paper A's title/authors but paper B's REAL doi (both resolve)
    add("doi_swap", "hard", True, "A's title+authors, B's real DOI — resolves fine, metadata won't match",
        _bib("ref1", pA["title"][0], _authors(pA), _year(pA), pB["DOI"], _venue(pA)))

    # C4 TITLE MISMATCH — real DOI, plausible wrong title (B's title on A's DOI)
    add("title_mismatch", "medium", True, "A's real DOI but B's title",
        _bib("ref1", pB["title"][0], _authors(pA), _year(pA), pA["DOI"], _venue(pA)))

    # C5 AUTHOR MISMATCH — real DOI, one fabricated extra author appended
    add("author_mismatch", "medium", True, "real DOI + one fabricated extra author",
        _bib("ref1", pA["title"][0], _authors(pA) + ["John Q. Fabricated"], _year(pA), pA["DOI"], _venue(pA)))

    # C6 YEAR MISMATCH — real DOI, year off by 2
    add("year_mismatch", "medium", True, "real DOI, year off by 2",
        _bib("ref1", pA["title"][0], _authors(pA), str(int(_year(pA)) + 2), pA["DOI"], _venue(pA)))

    # C7 FABRICATED — plausible entry, DOI does not exist in Crossref
    add("fabricated", "hard", True, "hallucinated ref: plausible title, non-existent DOI",
        _bib("ref1", "Attention-Guided Contrastive Learning for Robust Text Classification",
             ["Alice Zhang", "Wei Chen", "Michael Brown"], "2022",
             "10.18653/v1/2022.acl-long.9999", "ACL"))

    # C8 MALFORMED DOI — easy tier
    add("malformed_doi", "easy", False, "DOI not in 10.NNNN/... format",
        _bib("ref1", pA["title"][0], _authors(pA), _year(pA), "doi-12345-broken", _venue(pA)))

    print("\nRunning ScholarLint reference gate on each case...\n")
    for c in cases:
        verdict = await _run_gate(c["bib"])
        c["scholarlint_verdict"] = verdict
        errs = [v for v in verdict if v.startswith("ERROR")]
        print(f"[{c['category']:16s} | {c['difficulty']:6s}] "
              f"ext_verify={c['requires_external_verification']}  "
              f"-> {len(errs)} ERROR(s)")
        for v in verdict:
            print("      " + v.encode("ascii", "replace").decode()[:110])
        print()

    OUT.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(cases)} sample cases -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
