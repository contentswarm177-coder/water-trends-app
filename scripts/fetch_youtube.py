"""Fetch YouTube mentions for tracked topics and write data/youtube_mentions.json.

Runs locally (needs YOUTUBE_API_KEY env var) and via GitHub Actions daily.
Uses YouTube Data API v3 (free tier, 10k units/day quota).

Quota cost per run: 17 keywords x 100 units (search.list) + small overhead
for videos.list batches = ~1,720 units, well under the 10k daily limit.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import ALL_TOPICS

OUTPUT = REPO_ROOT / "data" / "youtube_mentions.json"
VIDEOS_PER_KEYWORD = 25
DAYS_BACK = 7
DETAILS_BATCH_SIZE = 50


def build_client():
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("ERROR: YOUTUBE_API_KEY env var not set", flush=True)
        sys.exit(2)
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def search_keyword(yt, keyword: str, published_after: str) -> list[str]:
    try:
        resp = yt.search().list(
            part="id",
            q=f'"{keyword}"',
            type="video",
            order="relevance",
            publishedAfter=published_after,
            maxResults=VIDEOS_PER_KEYWORD,
            regionCode="US",
            relevanceLanguage="en",
        ).execute()
    except HttpError as exc:
        print(f"  HTTP error for '{keyword}': {exc}", flush=True)
        return []
    return [item["id"]["videoId"] for item in resp.get("items", []) if item.get("id", {}).get("videoId")]


def filter_relevant_keywords(video: dict) -> list[str]:
    """Return only the matched keywords that actually appear in title/description."""
    text = f"{video.get('title', '')} {video.get('description', '')}".lower()
    return [kw for kw in video.get("matched_keywords", []) if kw.lower() in text]


def fetch_video_details(yt, video_ids: list[str]) -> list[dict]:
    items: list[dict] = []
    for i in range(0, len(video_ids), DETAILS_BATCH_SIZE):
        batch = video_ids[i : i + DETAILS_BATCH_SIZE]
        try:
            resp = yt.videos().list(
                part="snippet,statistics",
                id=",".join(batch),
            ).execute()
        except HttpError as exc:
            print(f"  details batch error: {exc}", flush=True)
            continue
        items.extend(resp.get("items", []))
    return items


def main() -> int:
    yt = build_client()
    since_dt = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)
    since_iso = since_dt.isoformat(timespec="seconds").replace("+00:00", "Z")

    by_id: dict[str, list[str]] = {}
    by_keyword_count: dict[str, int] = {}

    for keyword in ALL_TOPICS:
        print(f"  '{keyword}'…", end="", flush=True)
        ids = search_keyword(yt, keyword, since_iso)
        by_keyword_count[keyword] = len(ids)
        for vid in ids:
            by_id.setdefault(vid, []).append(keyword)
        print(f" {len(ids)} videos", flush=True)

    print(f"\nFetching details for {len(by_id)} unique videos…", flush=True)
    details = fetch_video_details(yt, list(by_id.keys()))

    mentions: list[dict] = []
    for item in details:
        vid_id = item["id"]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        mentions.append(
            {
                "id": vid_id,
                "matched_keywords": by_id.get(vid_id, []),
                "channel_title": snippet.get("channelTitle"),
                "channel_id": snippet.get("channelId"),
                "title": snippet.get("title"),
                "description": (snippet.get("description") or "")[:500],
                "published_at": snippet.get("publishedAt"),
                "thumbnail": thumbnails.get("medium", {}).get("url"),
                "view_count": int(stats.get("viewCount", 0)) if "viewCount" in stats else 0,
                "like_count": int(stats["likeCount"]) if "likeCount" in stats else None,
                "comment_count": int(stats["commentCount"]) if "commentCount" in stats else None,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
            }
        )

    raw_count = len(mentions)
    relevant: list[dict] = []
    for m in mentions:
        valid = filter_relevant_keywords(m)
        if valid:
            m["matched_keywords"] = valid
            relevant.append(m)
    mentions = relevant
    print(
        f"Relevance filter: kept {len(mentions)}/{raw_count} "
        f"(dropped {raw_count - len(mentions)} with no keyword in title/description)",
        flush=True,
    )

    by_keyword_count = {kw: 0 for kw in ALL_TOPICS}
    for m in mentions:
        for kw in m["matched_keywords"]:
            by_keyword_count[kw] += 1

    mentions.sort(key=lambda m: m.get("view_count", 0), reverse=True)

    output = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "keywords": ALL_TOPICS,
        "days_back": DAYS_BACK,
        "total_unique_mentions": len(mentions),
        "by_keyword_count": by_keyword_count,
        "mentions": mentions,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2))
    print(
        f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, "
        f"{len(mentions)} unique videos)",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
