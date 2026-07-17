"""Scrape ALL ICLR desk-rejected papers 2020-2026 with rejection reasons.

Saves to: research/bench/iclr_desk_rejected.json
"""
import json, time, urllib.request, urllib.parse, re
from pathlib import Path
from collections import Counter

TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjp7ImlkIjoiaGZ5bWgyQG5vdHRpbmdoYW0uZWR1Lm15IiwicHJvZmlsZSI6eyJpZCI6In5NZW5nemVfSG9uZzEiLCJmdWxsbmFtZSI6Ik1lbmd6ZSBIb25nIiwiZW1haWxzIjpbImhmeW1oMkBub3R0aW5naGFtLmVkdS5teSIsIm1lbmd6ZWhvbmdAd2ViYW5rLmNvbSIsIm1lbmd6ZS5ob25nQGNvbm5lY3QucG9seXUuaGsiXSwicHJlZmVycmVkRW1haWwiOiJtZW5nemUuaG9uZ0Bjb25uZWN0LnBvbHl1LmhrIiwidXNlcm5hbWVzIjpbIn5NZW5nemVfSG9uZzEiXSwicHJlZmVycmVkSWQiOiJ-TWVuZ3plX0hvbmcxIiwic3RhdGUiOiJBY3RpdmUgSW5zdGl0dXRpb25hbCIsInRlcm1zVGltZXN0YW1wIjoxNzY1MjUxNTI2OTY1LCJ0b2tlblZlcnNpb24iOjB9fSwiaWF0IjoxNzg0MTkwMzMzLCJleHAiOjE3ODQyNzY3MzMsImlzcyI6Im9wZW5yZXZpZXctMTc2NTA0NzMyMTY4OCJ9.P0ov3SHcpaUEKyazyXtu4ZF5yuH4Z-CwSjH5m6Ww59Q6nCrv4HlnPpuSoS9SUvBTynB__NLK974nVg3X0dzr-R-0LICSx0DyAYAtVxkLyh-tsqkw9Ox2yOc24zcbx1H9O6tTOGoqTBcaxTovGq9O0EEUDMuaNA1-5IIBvWNCG3Z1kvAwh2cjuChNUSyqu1UGOmb-XzLITOPSrWXAN-Lxpn8A1_GJzNd07iMGObgboqts_oiyB2-8lYEHcNLckvprusgQbwixoMdS5iH1m989bHWaUiaFMyB1ZhLgVShPrumEoO-mbiB57UNhXeHeuD7fzqVJE7r-tGQ4mt9gXjvbXQ"

BASE = "https://api2.openreview.net"
OUT  = Path(__file__).parent / "iclr_desk_rejected.json"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "ScholarLintResearch/1.0"}

def api(path, retries=3):
    url = BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

def gv(x):
    return (x.get("value", "") if isinstance(x, dict) else str(x or ""))

def get_all(path_template, page_size=100):
    """Paginate through all results."""
    results, offset = [], 0
    while True:
        d = api(path_template + f"&limit={page_size}&offset={offset}")
        notes = d.get("notes", [])
        results.extend(notes)
        print(f"    fetched {len(results)} so far...", end="\r")
        if len(notes) < page_size:
            break
        offset += page_size
        time.sleep(0.3)
    return results

# Desk-rejected venueid patterns per year (discovered empirically)
# Some years use different field names — we try multiple strategies
YEAR_CONFIGS = [
    # (year, venueid_pattern, submission_invitation)
    (2026, "ICLR.cc/2026/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2026%2FConference%2F-%2FSubmission"),
    (2025, "ICLR.cc/2025/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2025%2FConference%2F-%2FSubmission"),
    (2024, "ICLR.cc/2024/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2024%2FConference%2F-%2FSubmission"),
    (2023, "ICLR.cc/2023/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2023%2FConference%2F-%2FSubmission"),
    (2022, "ICLR.cc/2022/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2022%2FConference%2F-%2FSubmission"),
    (2021, "ICLR.cc/2021/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2021%2FConference%2F-%2FSubmission"),
    (2020, "ICLR.cc/2020/Conference/Desk_Rejected_Submission",
           "ICLR.cc%2F2020%2FConference%2F-%2FSubmission"),
]

# Possible field names for rejection reason across different years
REASON_FIELDS = [
    "desk_reject_comments", "comment", "reason", "message",
    "withdrawal_confirmation", "rejection_reason", "note",
]

def extract_reason(content):
    for f in REASON_FIELDS:
        v = gv(content.get(f, "")).strip()
        if v and len(v) > 10:
            return v
    # fallback: longest string value
    candidates = [(k, gv(v)) for k, v in content.items()
                  if isinstance(v, (str, dict)) and len(gv(v)) > 20]
    if candidates:
        return max(candidates, key=lambda x: len(x[1]))[1]
    return ""

def get_rejection_reason(forum_id):
    """Get the desk-rejection note for a submission."""
    try:
        notes = api(f"/notes?forum={forum_id}&limit=30").get("notes", [])
        for n in notes:
            inv = (n.get("invitations") or [""])[0]
            if "Desk_Rejection" in inv and "Reversion" not in inv:
                return extract_reason(n.get("content", {}))
        # fallback: check submission note itself
        for n in notes:
            c = n.get("content", {})
            venue = gv(c.get("venue", ""))
            if "desk" in venue.lower() or "rejected" in venue.lower():
                reason = extract_reason(c)
                if reason:
                    return reason
    except Exception:
        pass
    return ""

def categorize(reason):
    r = reason.lower()
    if any(x in r for x in ["do not refer to real", "hallucinated", "fabricated",
                              "not real", "does not exist", "non-existent",
                              "major errors in bibliographic"]):
        return "fabricated_reference"
    if any(x in r for x in ["anonymi", "non-anon", "author name", "code link",
                              "github", "gitee", "license", "not anonymized"]):
        return "anonymity_violation"
    if any(x in r for x in ["page limit", "exceeds", "over the limit"]):
        return "exceeds_page_limit"
    if any(x in r for x in ["template", "margin", "format", "page size",
                              "wrong format", "incompatible"]):
        return "wrong_format_template"
    if any(x in r for x in ["dual submission", "overlap", "previously published"]):
        return "dual_submission"
    if reason.strip():
        return "other"
    return "unknown"

all_records = []
year_stats = {}

for (year, venueid, sub_inv) in YEAR_CONFIGS:
    print(f"\n=== ICLR {year} ===")
    vid_enc = urllib.parse.quote(venueid)

    # Strategy 1: filter by venueid
    papers = []
    try:
        papers = get_all(f"/notes?content.venueid={vid_enc}&invitation={sub_inv}")
        print(f"  venueid strategy: {len(papers)} papers")
    except Exception as e:
        print(f"  venueid strategy failed: {e}")

    # Strategy 2: if nothing found, use Desk_Rejection_Reversion invitations
    if not papers:
        try:
            prefix = urllib.parse.quote(f"ICLR.cc/{year}/Conference/Submission")
            suffix = urllib.parse.quote("Desk_Rejection_Reversion")
            invs = api(f"/invitations?prefix={prefix}&suffix={suffix}&limit=1000").get("invitations", [])
            print(f"  invitation strategy: {len(invs)} invitations found")
            # extract forum IDs from invitation paths
            forum_ids = []
            for inv in invs:
                m = re.search(r"/(Submission\w+)/-/Desk_Rejection", inv.get("id", ""))
                if m:
                    forum_ids.append(m.group(1))
            # fetch each submission note
            for fid in forum_ids[:200]:  # cap at 200 for safety
                try:
                    notes = api(f"/notes?forum={fid}&limit=5").get("notes", [])
                    for n in notes:
                        invitations = n.get("invitations", [])
                        if any("Submission" in i and "/-/" not in i.split("Submission")[-1][:5]
                               for i in invitations):
                            papers.append(n)
                            break
                    time.sleep(0.1)
                except Exception:
                    pass
        except Exception as e:
            print(f"  invitation strategy failed: {e}")

    if not papers:
        print(f"  → no papers found for {year}, skipping")
        year_stats[year] = {"total": 0, "with_reason": 0, "categories": {}}
        continue

    print(f"  fetching rejection reasons for {len(papers)} papers...")
    records = []
    for i, p in enumerate(papers):
        c = p.get("content", {})
        forum = p.get("id") or p.get("forum", "")
        title = gv(c.get("title", ""))[:100]
        number = p.get("number", "")
        reason = get_rejection_reason(forum)
        cat = categorize(reason)

        # extract specific hallucinated citations if present
        cited_hallucinations = []
        if cat == "fabricated_reference":
            # each line that looks like an author+title reference
            for line in reason.split("\n"):
                line = line.strip()
                if len(line) > 40 and re.search(r"[A-Z][a-z]+,?\s+[A-Z]", line):
                    cited_hallucinations.append(line[:200])

        rec = {
            "year": year,
            "number": number,
            "forum": forum,
            "title": title,
            "rejection_reason": reason[:1000],
            "category": cat,
            "hallucinated_citations": cited_hallucinations[:5],
            "url": f"https://openreview.net/forum?id={forum}",
        }
        records.append(rec)
        all_records.append(rec)

        if (i + 1) % 20 == 0:
            print(f"  processed {i+1}/{len(papers)}")
        time.sleep(0.12)

    cats = Counter(r["category"] for r in records)
    year_stats[year] = {
        "total": len(records),
        "with_reason": sum(1 for r in records if r["rejection_reason"]),
        "categories": dict(cats.most_common()),
    }
    print(f"  done: {len(records)} papers | {dict(cats.most_common())}")

# Save
OUT.write_text(json.dumps({
    "meta": {"total": len(all_records), "years": list(range(2020, 2027))},
    "year_stats": year_stats,
    "records": all_records,
}, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"\n{'='*60}")
print(f"TOTAL: {len(all_records)} desk-rejected papers across ICLR 2020-2026")
print(f"Saved to {OUT}")
print("\nYear breakdown:")
for y, s in sorted(year_stats.items()):
    print(f"  {y}: {s['total']} papers | cats: {s['categories']}")
print("\nTop fabricated-reference cases with extracted citations:")
fab = [r for r in all_records if r["category"] == "fabricated_reference"
       and r["hallucinated_citations"]][:5]
for r in fab:
    print(f"\n  [{r['year']}#{r['number']}] {r['title'][:60]}")
    for c in r["hallucinated_citations"][:2]:
        print(f"    → {c[:120]}")
