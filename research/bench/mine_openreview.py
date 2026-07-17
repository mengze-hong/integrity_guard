"""Mine ICLR 2024 reviews for integrity-related reviewer comments.

Uses the OpenReview API v2 with a Bearer token.
Looks for: number/result inconsistencies, citation errors, reference issues,
figure/table mismatches — things within ScholarLint's gate scope.
"""
import json
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjp7ImlkIjoiaGZ5bWgyQG5vdHRpbmdoYW0uZWR1Lm15IiwicHJvZmlsZSI6eyJpZCI6In5NZW5nemVfSG9uZzEiLCJmdWxsbmFtZSI6Ik1lbmd6ZSBIb25nIiwiZW1haWxzIjpbImhmeW1oMkBub3R0aW5naGFtLmVkdS5teSIsIm1lbmd6ZWhvbmdAd2ViYW5rLmNvbSIsIm1lbmd6ZS5ob25nQGNvbm5lY3QucG9seXUuaGsiXSwicHJlZmVycmVkRW1haWwiOiJtZW5nemUuaG9uZ0Bjb25uZWN0LnBvbHl1LmhrIiwidXNlcm5hbWVzIjpbIn5NZW5nemVfSG9uZzEiXSwicHJlZmVycmVkSWQiOiJ-TWVuZ3plX0hvbmcxIiwic3RhdGUiOiJBY3RpdmUgSW5zdGl0dXRpb25hbCIsInRlcm1zVGltZXN0YW1wIjoxNzY1MjUxNTI2OTY1LCJ0b2tlblZlcnNpb24iOjB9fSwiaWF0IjoxNzg0MTkwMzMzLCJleHAiOjE3ODQyNzY3MzMsImlzcyI6Im9wZW5yZXZpZXctMTc2NTA0NzMyMTY4OCJ9.P0ov3SHcpaUEKyazyXtu4ZF5yuH4Z-CwSjH5m6Ww59Q6nCrv4HlnPpuSoS9SUvBTynB__NLK974nVg3X0dzr-R-0LICSx0DyAYAtVxkLyh-tsqkw9Ox2yOc24zcbx1H9O6tTOGoqTBcaxTovGq9O0EEUDMuaNA1-5IIBvWNCG3Z1kvAwh2cjuChNUSyqu1UGOmb-XzLITOPSrWXAN-Lxpn8A1_GJzNd07iMGObgboqts_oiyB2-8lYEHcNLckvprusgQbwixoMdS5iH1m989bHWaUiaFMyB1ZhLgVShPrumEoO-mbiB57UNhXeHeuD7fzqVJE7r-tGQ4mt9gXjvbXQ"

BASE = "https://api2.openreview.net"
OUT = Path(__file__).parent / "openreview_integrity_hits.json"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "ScholarLintResearch/1.0"
}

# Keywords grouped by ScholarLint gate category
GATE_KW = {
    "data_integrity":       ["inconsisten", "mismatch", "wrong number", "incorrect result",
                              "different from", "does not match", "table shows", "contradicts",
                              "discrepan", "reported.*different", "number.*wrong", "result.*inconsist"],
    "citation":             ["missing citation", "missing reference", "undefined", "uncited",
                             "no citation", "citation missing", "not cited", "cite.*missing"],
    "reference_authentic":  ["retract", "fabricat", "hallucin", "wrong.*author", "incorrect.*title",
                              "wrong.*title", "doi.*wrong", "doi.*incorrect", "non-existent"],
    "figure_table":         ["figure.*missing", "table.*missing", "not referenced", "missing.*label",
                              "caption.*wrong", "figure.*wrong", "broken.*ref"],
}

ALL_KW = [kw for kws in GATE_KW.values() for kw in kws]


def api_get(path: str) -> dict:
    url = BASE + path
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def get_text(field_val) -> str:
    if isinstance(field_val, dict):
        return field_val.get("value", "") or ""
    return str(field_val or "")


def find_kw_gate(text: str):
    t = text.lower()
    import re
    for gate, kws in GATE_KW.items():
        for kw in kws:
            if re.search(kw, t):
                return gate, kw
    return None, None


def mine_papers(venue_encoded: str, limit: int = 50) -> list[dict]:
    path = f"/notes?content.venue={venue_encoded}&limit={limit}"
    papers = api_get(path).get("notes", [])
    print(f"  fetched {len(papers)} papers from {urllib.parse.unquote(venue_encoded)}")
    return papers


def mine_forum(forum_id: str) -> list[dict]:
    notes = api_get(f"/notes?forum={forum_id}&limit=30").get("notes", [])
    hits = []
    for n in notes:
        inv = (n.get("invitations") or [""])[0]
        if "Official_Review" not in inv:
            continue
        c = n.get("content", {})
        for field in ["weaknesses", "summary", "questions", "strengths"]:
            text = get_text(c.get(field, ""))
            gate, kw = find_kw_gate(text)
            if gate:
                idx = text.lower().find(kw.split(".*")[0])
                snippet = text[max(0, idx-80):idx+200].strip()
                hits.append({
                    "forum": forum_id,
                    "review_id": n.get("id"),
                    "field": field,
                    "gate": gate,
                    "keyword": kw,
                    "snippet": snippet,
                    "venue": "",
                })
    return hits


def main():
    all_hits = []
    venues = [
        ("ICLR%202024%20Poster", 80),
        ("ICLR%202024%20oral", 30),
        ("ICLR%202024%20spotlight", 30),
    ]
    for venue_enc, limit in venues:
        papers = mine_papers(venue_enc, limit)
        for p in papers:
            fid = p.get("id")
            if not fid:
                continue
            try:
                hits = mine_forum(fid)
                for h in hits:
                    h["venue"] = urllib.parse.unquote(venue_enc)
                all_hits.extend(hits)
            except Exception as e:
                pass
            time.sleep(0.15)

    # Summary
    print(f"\n=== RESULTS: {len(all_hits)} integrity-related snippets ===")
    by_gate = Counter(h["gate"] for h in all_hits)
    print("By gate:", dict(by_gate.most_common()))
    by_kw = Counter(h["keyword"] for h in all_hits)
    print("Top keywords:", dict(by_kw.most_common(10)))

    # Show best examples per gate
    print("\n=== SAMPLE SNIPPETS (most interesting per gate) ===\n")
    seen = defaultdict(set)
    for h in all_hits:
        g, kw = h["gate"], h["keyword"]
        if kw in seen[g] or len(seen[g]) >= 3:
            continue
        seen[g].add(kw)
        print(f"[{g}] keyword='{kw}' forum={h['forum']}")
        print(f"  {h['snippet'][:300]}")
        print()

    OUT.write_text(json.dumps(all_hits, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(all_hits)} hits -> {OUT}")


if __name__ == "__main__":
    main()
