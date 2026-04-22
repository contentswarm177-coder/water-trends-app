"""Fetch Reddit mentions via public JSON endpoints (no auth required).

Reddit steers new developers to Devvit rather than the old script-app path,
so we skip credentials entirely and use the public /search.json endpoint.
Rate limit is ~10 req/min unauthenticated; we space requests 7s apart to
stay safely inside the budget.
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

OUTPUT = REPO_ROOT / "data" / "reddit_mentions.json"
SEARCH_URL = "https://www.reddit.com/search.json"
USER_AGENT = (
    "water-trends-scan/1.0 "
    "(https://github.com/contentswarm177-coder/water-trends-app)"
)
POSTS_PER_KEYWORD = 100
TIME_FILTER = "week"
KEYWORD_DELAY_SEC = 7.0
MAX_RETRIES = 3


def search_keyword(keyword: str) -> list[dict]:
    params = {
        "q": keyword,
        "sort": "new",
        "t": TIME_FILTER,
        "limit": POSTS_PER_KEYWORD,
        "raw_json": 1,
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    429 rate-limited; waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                print(f"    403 blocked for '{keyword}' (likely UA-rejected)", flush=True)
                return []
            resp.raise_for_status()
            payload = resp.json()
            return [child.get("data", {}) for child in payload.get("data", {}).get("children", [])]
        except requests.RequestException as exc:
            wait = 5 * (2 ** attempt)
            print(f"    attempt {attempt + 1} failed: {exc}; retry in {wait}s", flush=True)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(wait)
    return []


def normalize_post(raw: dict) -> dict | None:
    post_id = raw.get("id")
    if not post_id:
        return None
    return {
        "id": post_id,
        "subreddit": raw.get("subreddit"),
        "title": raw.get("title", ""),
        "selftext": (raw.get("selftext") or "")[:500],
        "score": raw.get("score", 0),
        "num_comments": raw.get("num_comments", 0),
        "created_utc": raw.get("created_utc"),
        "permalink": f"https://reddit.com{raw.get('permalink', '')}",
        "url": raw.get("url", ""),
        "author": raw.get("author", "[deleted]"),
    }


def main() -> int:
    print(f"Searching {len(ALL_TOPICS)} keywords via Reddit public JSON…", flush=True)

    by_id: dict[str, dict] = {}
    by_keyword_count: dict[str, int] = {}

    for keyword in ALL_TOPICS:
        print(f"  '{keyword}'…", end="", flush=True)
        raw_posts = search_keyword(keyword)
        normalized = [p for p in (normalize_post(r) for r in raw_posts) if p]
        by_keyword_count[keyword] = len(normalized)
        for post in normalized:
            if post["id"] in by_id:
                by_id[post["id"]]["matched_keywords"].append(keyword)
            else:
                post["matched_keywords"] = [keyword]
                by_id[post["id"]] = post
        print(f" {len(normalized)} posts", flush=True)
        time.sleep(KEYWORD_DELAY_SEC)

    mentions = list(by_id.values())
    mentions.sort(key=lambda m: m.get("created_utc") or 0, reverse=True)

    output = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "keywords": ALL_TOPICS,
        "time_filter": TIME_FILTER,
        "total_unique_mentions": len(mentions),
        "by_keyword_count": by_keyword_count,
        "mentions": mentions,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2))
    print(
        f"\nWrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, "
        f"{len(mentions)} unique posts)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
