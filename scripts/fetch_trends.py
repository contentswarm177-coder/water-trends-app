"""Fetch Google Trends data and write data/trends.json.

Runs locally to seed, and via GitHub Actions on a daily cron. Designed to be
resilient to Google's aggressive rate limiting: a fresh pytrends session is
created per batch, batches are spaced generously, and failures retry with
exponential backoff.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pytrends.request import TrendReq

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import ALL_TOPICS, BATCH_SIZE, GEO, TIMEFRAMES, TOPIC_GROUPS

BATCH_DELAY_SEC = 60.0
TIMEFRAME_DELAY_SEC = 90.0
MAX_RETRIES = 5
BACKOFF_BASE_SEC = 30.0
OUTPUT = REPO_ROOT / "data" / "trends.json"


def fetch_batch(batch: list[str], timeframe: str) -> pd.DataFrame:
    for attempt in range(MAX_RETRIES):
        try:
            pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
            pytrends.build_payload(batch, timeframe=timeframe, geo=GEO)
            df = pytrends.interest_over_time()
            return df.drop(columns=["isPartial"], errors="ignore") if not df.empty else df
        except Exception as exc:
            wait = BACKOFF_BASE_SEC * (2 ** attempt)
            print(
                f"    attempt {attempt + 1}/{MAX_RETRIES} failed "
                f"({exc.__class__.__name__}); retrying in {wait:.0f}s",
                flush=True,
            )
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(wait)
    return pd.DataFrame()


def fetch_timeframe(timeframe: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    batches = [ALL_TOPICS[i : i + BATCH_SIZE] for i in range(0, len(ALL_TOPICS), BATCH_SIZE)]
    for idx, batch in enumerate(batches, 1):
        print(f"  batch {idx}/{len(batches)}: {batch}", flush=True)
        df = fetch_batch(batch, timeframe)
        if not df.empty:
            frames.append(df)
        if idx < len(batches):
            print(f"  sleeping {BATCH_DELAY_SEC:.0f}s before next batch…", flush=True)
            time.sleep(BATCH_DELAY_SEC)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def main() -> int:
    result: dict = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "geo": GEO,
        "topics": ALL_TOPICS,
        "topic_groups": TOPIC_GROUPS,
        "timeframes": {},
    }

    timeframe_items = list(TIMEFRAMES.items())
    for idx, (label, tf) in enumerate(timeframe_items, 1):
        print(f"\n[{idx}/{len(timeframe_items)}] Fetching {label} ({tf})…", flush=True)
        df = fetch_timeframe(tf)
        if df.empty:
            print(f"  FAILED: no data returned for {tf}", flush=True)
            return 1
        result["timeframes"][tf] = {
            "dates": [d.isoformat() for d in df.index],
            "series": {
                col: [int(v) if pd.notna(v) else None for v in df[col]]
                for col in df.columns
            },
        }
        if idx < len(timeframe_items):
            print(f"  sleeping {TIMEFRAME_DELAY_SEC:.0f}s before next timeframe…", flush=True)
            time.sleep(TIMEFRAME_DELAY_SEC)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
