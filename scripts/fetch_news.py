"""Fetch news coverage for tracked topics via GDELT 2.0 Doc API.

GDELT is free, requires no API key, and has no rate-limit quota (though
it recommends polite spacing between requests). We query per keyword with
phrase-match + US sources + English, dedupe by URL, and write the result.
"""
from __future__ import annotations

import json
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
KEYWORD_DELAY_SEC = 2.0
MAX_RETRIES = 3
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
            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code} for '{keyword}'", flush=True)
                return []
            text = resp.text.strip()
            if not text or not text.startswith("{"):
                print(f"    non-JSON response for '{keyword}' (rate-limited or error)", flush=True)
                time.sleep(5)
                continue
            payload = json.loads(text)
            return payload.get("articles", []) or []
        except (requests.RequestException, json.JSONDecodeError) as exc:
            wait = 5 * (2 ** attempt)
            print(f"    attempt {attempt + 1} failed: {exc}; retry in {wait}s", flush=True)
            if attempt == MAX_RETRIES - 1:
                return []
            time.sleep(wait)
    return []


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

    # GDELT already did phrase matching on the full article text; no further
    # title-side filter — news headlines often use synonyms (e.g. "forever
    # chemicals" rather than "PFAS", "Flint crisis" rather than "lead in
    # water") and the title filter we used for YouTube over-rejects here.
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
