"""Add ICLR 2022 and 2023 desk-rejected papers to the existing dataset.

2022/2023 use a different API structure — the v2 /notes endpoint returns nothing
for those years' submission invitations, but we can query by content.venue text
(which is what worked for 2024-2026). We do a full paginated scan of all
submissions and filter for venue text containing 'desk'.

Also re-checks the actual rejection reason by fetching forum replies.
"""
import httpx, json, time, re
from pathlib import Path
from collections import Counter

TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjp7ImlkIjoiaGZ5bWgyQG5vdHRpbmdoYW0uZWR1Lm15IiwicHJvZmlsZSI6eyJpZCI6In5NZW5nemVfSG9uZzEiLCJmdWxsbmFtZSI6Ik1lbmd6ZSBIb25nIiwiZW1haWxzIjpbImhmeW1oMkBub3R0aW5naGFtLmVkdS5teSIsIm1lbmd6ZWhvbmdAd2ViYW5rLmNvbSIsIm1lbmd6ZS5ob25nQGNvbm5lY3QucG9seXUuaGsiXSwicHJlZmVycmVkRW1haWwiOiJtZW5nemUuaG9uZ0Bjb25uZWN0LnBvbHl1LmhrIiwidXNlcm5hbWVzIjpbIn5NZW5nemVfSG9uZzEiXSwicHJlZmVycmVkSWQiOiJ-TWVuZ3plX0hvbmcxIiwic3RhdGUiOiJBY3RpdmUgSW5zdGl0dXRpb25hbCIsInRlcm1zVGltZXN0YW1wIjoxNzY1MjUxNTI2OTY1LCJ0b2tlblZlcnNpb24iOjB9fSwiaWF0IjoxNzg0MTkwMzMzLCJleHAiOjE3ODQyNzY3MzMsImlzcyI6Im9wZW5yZXZpZXctMTc2NTA0NzMyMTY4OCJ9.P0ov3SHcpaUEKyazyXtu4ZF5yuH4Z-CwSjH5m6Ww59Q6nCrv4HlnPpuSoS9SUvBTynB__NLK974nVg3X0dzr-R-0LICSx0DyAYAtVxkLyh-tsqkw9Ox2yOc24zcbx1H9O6tTOGoqTBcaxTovGq9O0EEUDMuaNA1-5IIBvWNCG3Z1kvAwh2cjuChNUSyqu1UGOmb-XzLITOPSrWXAN-Lxpn8A1_GJzNd07iMGObgboqts_oiyB2-8lYEHcNLckvprusgQbwixoMdS5iH1m989bHWaUiaFMyB1ZhLgVShPrumEoO-mbiB57UNhXeHeuD7fzqVJE7r-tGQ4mt9gXjvbXQ"

BASE = "https://api2.openreview.net"
OUT  = Path(__file__).parent / "iclr_desk_rejected.json"
REASON_FIELDS = ["desk_reject_comments", "comment", "reason", "message", "note"]


def gv(x):
    return (x.get("value", "") if isinstance(x, dict) else str(x or ""))


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
    return "other" if reason.strip() else "unknown"


def extract_reason(content):
    for f in REASON_FIELDS:
        v = gv(content.get(f, "")).strip()
        if v and len(v) > 10:
            return v
    candidates = [(k, gv(v)) for k, v in content.items()
                  if isinstance(v, (str, dict)) and len(gv(v)) > 20]
    if candidates:
        return max(candidates, key=lambda x: len(x[1]))[1]
    return ""


def _scan_v1(year: int, client_v2) -> list[dict]:
    """Scan ICLR 2022/2023 using API v1 (older years use different auth endpoint)."""
    import httpx
    v1_headers = {"Authorization": f"Bearer {TOKEN}",
                  "User-Agent": "ScholarLintResearch/1.0"}
    desk, offset, total_scanned = [], 0, 0
    inv = f"ICLR.cc/{year}/Conference/-/Blind_Submission"
    while True:
        r = httpx.get("https://api.openreview.net/notes",
                      params={"invitation": inv, "limit": 1000, "offset": offset},
                      headers=v1_headers, timeout=30)
        if r.status_code != 200:
            print(f"  v1 error {r.status_code}")
            break
        batch = r.json().get("notes", [])
        total_scanned += len(batch)
        for n in batch:
            c = n.get("content", {})
            venue = str(c.get("venue", "")).lower()
            if "desk" in venue:
                desk.append(n)
        print(f"  v1 scanned {total_scanned}, desk={len(desk)}...", end="\r")
        if len(batch) < 1000:
            break
        offset += 1000
        time.sleep(0.2)
    print(f"\n  ICLR {year} (v1): {total_scanned} total → {len(desk)} desk-rejected")

    records = []
    for p in desk:
        c = p.get("content", {})
        forum = p.get("id", "")
        title = str(c.get("title", ""))[:100]
        number = p.get("number", "")
        # get reason from v1 forum replies
        reason = ""
        try:
            rep = httpx.get("https://api.openreview.net/notes",
                            params={"forum": forum, "limit": 30},
                            headers=v1_headers, timeout=20)
            if rep.status_code == 200:
                for n in rep.json().get("notes", []):
                    inv2 = str(n.get("invitation", ""))
                    if "desk" in inv2.lower() or "Desk" in inv2:
                        reason = extract_reason(n.get("content", {}))
                        break
        except Exception:
            pass
        if not reason:
            reason = extract_reason(c)
        hallucinated = []
        if categorize(reason) == "fabricated_reference":
            for line in reason.split("\n"):
                line = line.strip()
                if len(line) > 40 and re.search(r"[A-Z][a-z]+,?\s+[A-Z]", line):
                    hallucinated.append(line[:200])
        records.append({
            "year": year, "number": number, "forum": forum,
            "title": title, "rejection_reason": reason[:1000],
            "category": categorize(reason),
            "hallucinated_citations": hallucinated[:5],
            "url": f"https://openreview.net/forum?id={forum}",
        })
        time.sleep(0.12)
    cats = Counter(r["category"] for r in records)
    print(f"  Done: {len(records)} | {dict(cats.most_common())}")
    return records


def main():
    # load existing dataset
    existing = json.loads(OUT.read_text(encoding="utf-8"))
    already_years = {r["year"] for r in existing["records"]}
    print(f"Existing: {existing['meta']['total']} records, years: {sorted(already_years)}")

    new_records = []

    with httpx.Client(
        base_url=BASE,
        headers={"Authorization": f"Bearer {TOKEN}",
                 "User-Agent": "ScholarLintResearch/1.0"},
        timeout=30.0,
    ) as client:

        for year in [2023, 2022]:
            if year in already_years:
                print(f"ICLR {year}: already in dataset, skipping")
                continue

            print(f"\n=== ICLR {year} — full scan ===")
            # 2022/2023: try multiple invitation patterns
            inv_patterns = [
                f"ICLR.cc/{year}/Conference/-/Submission",
                f"ICLR.cc/{year}/Conference/-/Blind_Submission",
            ]
            working_inv = None
            for pat in inv_patterns:
                r = client.get("/notes", params={"invitation": pat, "limit": 3})
                if r.status_code == 200 and r.json().get("notes"):
                    working_inv = pat
                    print(f"  Using invitation: {pat}")
                    break

            if not working_inv:
                # Try direct group query to find what invitations exist
                for suffix in ["Submission", "Paper_Submission", "Full_Paper"]:
                    r = client.get("/notes", params={
                        "invitation": f"ICLR.cc/{year}/Conference/-/{suffix}",
                        "limit": 3})
                    if r.status_code == 200 and r.json().get("notes"):
                        working_inv = f"ICLR.cc/{year}/Conference/-/{suffix}"
                        print(f"  Found via suffix search: {working_inv}")
                        break

            if not working_inv:
                print(f"  Could not find submission invitation for {year}")
                # Try API v1
                r1 = httpx.get(
                    f"https://api.openreview.net/notes",
                    params={"invitation": f"ICLR.cc/{year}/Conference/-/Blind_Submission",
                            "limit": 3},
                    headers={"Authorization": f"Bearer {TOKEN}"},
                    timeout=15)
                if r1.status_code == 200 and r1.json().get("notes"):
                    print(f"  v1 API works! Using v1 for {year}")
                    # switch to v1 for this year
                    desk_papers = _scan_v1(year, client)
                    new_records.extend(desk_papers)
                    continue
                else:
                    print(f"  v1 also failed ({r1.status_code}), skipping {year}")
                    continue

            # Full scan
            desk, offset, total_scanned = [], 0, 0
            while True:
                r = client.get("/notes", params={
                    "invitation": working_inv, "limit": 1000, "offset": offset})
                if r.status_code != 200:
                    print(f"  Error {r.status_code} at offset {offset}, retrying...")
                    time.sleep(3)
                    r = client.get("/notes", params={
                        "invitation": working_inv, "limit": 1000, "offset": offset})
                    if r.status_code != 200:
                        break
                batch = r.json().get("notes", [])
                total_scanned += len(batch)
                for n in batch:
                    c = n.get("content", {})
                    venue = gv(c.get("venue", ""))
                    venueid = gv(c.get("venueid", ""))
                    if "desk" in venue.lower() or "desk" in venueid.lower():
                        desk.append(n)
                print(f"  Scanned {total_scanned}, desk={len(desk)}...", end="\r")
                if len(batch) < 1000:
                    break
                offset += 1000
                time.sleep(0.2)

            print(f"\n  ICLR {year}: {total_scanned} total → {len(desk)} desk-rejected")

            # Get rejection reasons
            year_records = []
            for i, p in enumerate(desk):
                c = p.get("content", {})
                forum = p.get("id") or p.get("forum", "")
                title = gv(c.get("title", ""))[:100]
                number = p.get("number", "")
                reason = ""
                try:
                    replies = client.get("/notes", params={"forum": forum, "limit": 30})
                    if replies.status_code == 200:
                        for n in replies.json().get("notes", []):
                            inv = (n.get("invitations") or [""])[0]
                            if "Desk_Rejection" in inv and "Reversion" not in inv:
                                reason = extract_reason(n.get("content", {}))
                                break
                        if not reason:
                            # fallback: check submission content itself
                            reason = extract_reason(c)
                except Exception:
                    pass

                hallucinated = []
                if categorize(reason) == "fabricated_reference":
                    for line in reason.split("\n"):
                        line = line.strip()
                        if len(line) > 40 and re.search(r"[A-Z][a-z]+,?\s+[A-Z]", line):
                            hallucinated.append(line[:200])

                rec = {
                    "year": year, "number": number, "forum": forum,
                    "title": title, "rejection_reason": reason[:1000],
                    "category": categorize(reason),
                    "hallucinated_citations": hallucinated[:5],
                    "url": f"https://openreview.net/forum?id={forum}",
                }
                year_records.append(rec)
                time.sleep(0.12)

            cats = Counter(r["category"] for r in year_records)
            print(f"  Done: {len(year_records)} | {dict(cats.most_common())}")
            new_records.extend(year_records)

    if not new_records:
        print("\nNo new records to add.")
        return

    # Merge and save
    all_records = existing["records"] + new_records
    by_year = {}
    for r in all_records:
        y = r["year"]
        by_year.setdefault(y, []).append(r)

    year_stats = {}
    for y, recs in sorted(by_year.items()):
        cats = Counter(r["category"] for r in recs)
        year_stats[y] = {
            "total": len(recs),
            "with_reason": sum(1 for r in recs if r["rejection_reason"]),
            "categories": dict(cats.most_common()),
        }

    OUT.write_text(json.dumps({
        "meta": {"total": len(all_records),
                 "years": sorted(by_year.keys())},
        "year_stats": year_stats,
        "records": all_records,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"TOTAL: {len(all_records)} records saved to {OUT}")
    for y, s in sorted(year_stats.items()):
        print(f"  {y}: {s['total']} | {s['categories']}")


if __name__ == "__main__":
    main()
