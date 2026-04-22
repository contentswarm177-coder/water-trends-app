"""Fetch Google Trends data via SerpApi and write data/trends.json.

Runs locally (needs SERPAPI_KEY in env) and via GitHub Actions daily.
SerpApi's Google Trends engine proxies through their own IP pool, so no
rate-limit problems like direct pytrends.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import ALL_TOPICS, BATCH_SIZE, GEO, TIMEFRAMES, TOPIC_GROUPS

API_URL = "https://serpapi.com/search"
BATCH_DELAY_SEC = 1.0
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 5.0
OUTPUT = REPO_ROOT / "data" / "trends.json"


def resolve_date_param(timeframe: str) -> str:
    """Convert pytrends-style timeframe to a SerpApi-compatible date param.

    SerpApi supports today 3-m / 12-m / 5-y but not 24-m, so translate that
    one to a custom range.
    """
    if timeframe == "today 24-m":
        today = date.today()
        return f"{(today - timedelta(days=730)).isoformat()} {today.isoformat()}"
    return timeframe


def fetch_batch(api_key: str, batch: list[str], timeframe: str) -> pd.DataFrame:
    params = {
        "engine": "google_trends",
        "data_type": "TIMESERIES",
        "q": ",".join(batch),
        "date": resolve_date_param(timeframe),
        "geo": GEO,
        "api_key": api_key,
    }
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            timeline = payload.get("interest_over_time", {}).get("timeline_data", [])
            if not timeline:
                return pd.DataFrame()
            rows = []
            for entry in timeline:
                ts = pd.Timestamp(int(entry["timestamp"]), unit="s")
                row: dict = {"_date": ts}
                for topic, value in zip(batch, entry["values"]):
                    row[topic] = value.get("extracted_value")
                rows.append(row)
            return pd.DataFrame(rows).set_index("_date")
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (401, 402, 403):
                raise RuntimeError(
                    f"SerpApi auth/credit error ({status}): {exc.response.text[:200]}"
                ) from exc
            wait = BACKOFF_BASE_SEC * (2 ** attempt)
            print(f"    HTTP {status} on attempt {attempt + 1}; retry in {wait:.0f}s", flush=True)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(wait)
        except (requests.ConnectionError, requests.Timeout) as exc:
            wait = BACKOFF_BASE_SEC * (2 ** attempt)
            print(f"    network error on attempt {attempt + 1} ({exc.__class__.__name__}); retry in {wait:.0f}s", flush=True)
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(wait)
    return pd.DataFrame()


def fetch_timeframe(api_key: str, timeframe: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    batches = [ALL_TOPICS[i : i + BATCH_SIZE] for i in range(0, len(ALL_TOPICS), BATCH_SIZE)]
    for idx, batch in enumerate(batches, 1):
        print(f"  batch {idx}/{len(batches)}: {batch}", flush=True)
        df = fetch_batch(api_key, batch, timeframe)
        if not df.empty:
            frames.append(df)
        if idx < len(batches):
            time.sleep(BATCH_DELAY_SEC)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def main() -> int:
    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        print("ERROR: SERPAPI_KEY env var not set", flush=True)
        return 2

    result: dict = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "geo": GEO,
        "topics": ALL_TOPICS,
        "topic_groups": TOPIC_GROUPS,
        "timeframes": {},
    }

    for idx, (label, tf) in enumerate(TIMEFRAMES.items(), 1):
        print(f"\n[{idx}/{len(TIMEFRAMES)}] Fetching {label} ({tf})…", flush=True)
        df = fetch_timeframe(api_key, tf)
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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(f"\nWrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
