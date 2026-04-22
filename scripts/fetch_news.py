"""Fetch news coverage for tracked topics via GDELT 2.0 Doc API.

GDELT is free, requires no API key, and has no rate-limit quota (though
it recommends polite spacing between requests). We query per keyword with
phrase-match + US sources + English, then apply Tier 1 curation:
- collapse syndicated near-duplicates (same AP story on 20 local papers)
- cap articles per-domain to prevent one source from dominating
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import ALL_TOPICS

OUTPUT = REPO_ROOT / "data" / "news_mentions.json"
API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMESPAN = "7d"
MAX_RECORDS = 250
KEYWORD_DELAY_SEC = 4.0
MAX_RETRIES = 4

TITLE_PREFIX_LEN = 40
PER_DOMAIN_CAP = 5
USER_AGENT = (
    "water-trends-scan/1.0 "
    "(https://github.com/contentswarm177-coder/water-trends-app)"
)


def parse_gdelt_datetime(raw: str | None) -> str | None:
    """GDELT returns 'YYYYMMDDTHHMMSSZ'; normalize to ISO 8601."""
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat(timespec="seconds")
    except ValueError:
        return None


def search_keyword(keyword: str) -> list[dict]:
    query = f'"{keyword}" sourcecountry:US sourcelang:eng'
    params = {
        "query": query,
        "mode": "ArtList",
        "timespan": TIMESPAN,
        "maxrecords": MAX_RECORDS,
        "sort": "DateDesc",
        "format": "json",
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(API_URL, params=params, headers=headers, timeout=60)
            if resp.status_code == 429:
                wait = 10 * (2 ** attempt)
                print(f"    429 for '{keyword}' (attempt {attempt + 1}); retry in {wait}s", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code} for '{keyword}' (giving up)", flush=True)
                return []
            text = resp.text.strip()
            if not text or not text.startswith("{"):
                wait = 10 * (2 ** attempt)
                print(
                    f"    non-JSON for '{keyword}' (attempt {attempt + 1}); retry in {wait}s",
                    flush=True,
                )
                time.sleep(wait)
                continue
            payload = json.loads(text)
            return payload.get("articles", []) or []
        except (requests.RequestException, json.JSONDecodeError) as exc:
            wait = 10 * (2 ** attempt)
            print(f"    attempt {attempt + 1} failed: {exc}; retry in {wait}s", flush=True)
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(wait)
    return []


def title_key(title: str | None) -> str:
    """Normalized prefix of a title, used as a dedup key for syndicated stories.

    AP/Reuters stories reposted on local papers usually share an identical
    first 40-60 characters of headline even when the tail diverges ("...
    Here are some alternatives" vs "... Try some alternatives"). Taking a
    prefix of the normalized title catches that cleanly without needing
    fuzzy similarity.
    """
    clean = re.sub(r"[^a-z0-9 ]", "", (title or "").lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:TITLE_PREFIX_LEN]


def collapse_syndication(articles: list[dict]) -> list[dict]:
    """Merge articles that share a title prefix into a single consolidated entry."""
    groups: dict[str, list[dict]] = {}
    for art in articles:
        key = title_key(art.get("title"))
        if not key:
            key = art.get("id") or ""
        groups.setdefault(key, []).append(art)

    consolidated: list[dict] = []
    for group in groups.values():
        group.sort(key=lambda a: a.get("published_at") or "")
        rep = dict(group[0])
        rep["syndicated_count"] = len(group)
        rep["syndicated_domains"] = sorted(
            {a["domain"] for a in group if a.get("domain")}
        )
        merged_keywords: set[str] = set()
        for a in group:
            merged_keywords.update(a.get("matched_keywords", []))
        rep["matched_keywords"] = sorted(merged_keywords)
        consolidated.append(rep)
    return consolidated


def apply_domain_cap(articles: list[dict], cap: int) -> list[dict]:
    """Cap stories per primary domain to prevent one outlet from dominating."""
    counts: dict[str, int] = {}
    kept: list[dict] = []
    for art in sorted(articles, key=lambda a: a.get("published_at") or "", reverse=True):
        domain = art.get("domain") or ""
        if counts.get(domain, 0) >= cap:
            continue
        counts[domain] = counts.get(domain, 0) + 1
        kept.append(art)
    return kept


def normalize_article(raw: dict) -> dict | None:
    url = raw.get("url")
    if not url:
        return None
    return {
        "id": url,
        "domain": raw.get("domain"),
        "title": raw.get("title", ""),
        "url": url,
        "published_at": parse_gdelt_datetime(raw.get("seendate")),
        "language": raw.get("language"),
        "source_country": raw.get("sourcecountry"),
        "thumbnail": raw.get("socialimage"),
    }


def main() -> int:
    print(f"Searching {len(ALL_TOPICS)} keywords on GDELT…", flush=True)

    by_id: dict[str, dict] = {}

    for keyword in ALL_TOPICS:
        print(f"  '{keyword}'…", end="", flush=True)
        raw_articles = search_keyword(keyword)
        normalized = [a for a in (normalize_article(r) for r in raw_articles) if a]
        for art in normalized:
            if art["id"] in by_id:
                if keyword not in by_id[art["id"]]["matched_keywords"]:
                    by_id[art["id"]]["matched_keywords"].append(keyword)
            else:
                art["matched_keywords"] = [keyword]
                by_id[art["id"]] = art
        print(f" {len(normalized)} articles", flush=True)
        time.sleep(KEYWORD_DELAY_SEC)

    mentions = list(by_id.values())
    raw_count = len(mentions)

    # Tier 1 curation: collapse syndicated reposts and cap per-domain
    mentions = collapse_syndication(mentions)
    after_dedup = len(mentions)
    mentions = apply_domain_cap(mentions, PER_DOMAIN_CAP)
    after_cap = len(mentions)
    print(
        f"Tier 1 curation: {raw_count} raw → {after_dedup} unique stories "
        f"(collapsed {raw_count - after_dedup} syndicated reposts) "
        f"→ {after_cap} after per-domain cap of {PER_DOMAIN_CAP}",
        flush=True,
    )

    by_keyword_count = {kw: 0 for kw in ALL_TOPICS}
    for art in mentions:
        for kw in art["matched_keywords"]:
            by_keyword_count[kw] += 1

    mentions.sort(key=lambda a: a.get("published_at") or "", reverse=True)

    output = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "keywords": ALL_TOPICS,
        "timespan": TIMESPAN,
        "total_unique_mentions": len(mentions),
        "by_keyword_count": by_keyword_count,
        "mentions": mentions,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2))
    print(
        f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, "
        f"{len(mentions)} unique articles)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
