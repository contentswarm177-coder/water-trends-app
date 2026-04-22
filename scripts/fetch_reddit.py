"""Fetch Reddit mentions for tracked topics and write data/reddit_mentions.json.

Runs locally (needs REDDIT_* env vars) and via GitHub Actions daily.
Uses PRAW's Reddit Developer tier (free, low-volume authenticated access).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import praw
import prawcore

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import ALL_TOPICS

OUTPUT = REPO_ROOT / "data" / "reddit_mentions.json"
POSTS_PER_KEYWORD = 50
TIME_FILTER = "week"
KEYWORD_DELAY_SEC = 1.0


def build_client() -> praw.Reddit:
    required = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"ERROR: missing env vars: {missing}", flush=True)
        sys.exit(2)
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
        check_for_async=False,
    )


def search_keyword(reddit: praw.Reddit, keyword: str) -> list[dict]:
    results: list[dict] = []
    try:
        for submission in reddit.subreddit("all").search(
            keyword,
            sort="new",
            time_filter=TIME_FILTER,
            limit=POSTS_PER_KEYWORD,
        ):
            results.append(
                {
                    "id": submission.id,
                    "subreddit": submission.subreddit.display_name,
                    "title": submission.title,
                    "selftext": (submission.selftext or "")[:500],
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "created_utc": submission.created_utc,
                    "permalink": f"https://reddit.com{submission.permalink}",
                    "url": submission.url,
                    "author": str(submission.author) if submission.author else "[deleted]",
                }
            )
    except prawcore.exceptions.PrawcoreException as exc:
        print(f"  PRAW error for '{keyword}': {exc}", flush=True)
    return results


def main() -> int:
    reddit = build_client()
    print(f"Authenticated as read-only client; searching {len(ALL_TOPICS)} keywords…", flush=True)

    by_id: dict[str, dict] = {}
    by_keyword_count: dict[str, int] = {}

    for keyword in ALL_TOPICS:
        print(f"  '{keyword}'…", end="", flush=True)
        posts = search_keyword(reddit, keyword)
        by_keyword_count[keyword] = len(posts)
        for post in posts:
            if post["id"] in by_id:
                by_id[post["id"]]["matched_keywords"].append(keyword)
            else:
                post["matched_keywords"] = [keyword]
                by_id[post["id"]] = post
        print(f" {len(posts)} posts", flush=True)
        time.sleep(KEYWORD_DELAY_SEC)

    mentions = list(by_id.values())
    mentions.sort(key=lambda m: m["created_utc"], reverse=True)

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
