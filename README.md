# Water Quality Trends

A public Streamlit dashboard tracking US Google Trends search interest for
water quality topics (contaminants, filtration, water context).

## Architecture

Three independent daily GitHub Actions workflows each fetch from a different
source and commit a JSON snapshot to the repo. The Streamlit app reads the
committed files — no live API calls at view time.

```
GitHub Actions (staggered daily crons)
  ├─ 06:00 UTC  SerpApi Google Trends      →  data/trends.json
  ├─ 07:30 UTC  Reddit via PRAW            →  data/reddit_mentions.json
  └─ 09:00 UTC  YouTube Data API v3        →  data/youtube_mentions.json
      │
      │ commits to main
      ▼
  Streamlit Cloud auto-redeploys, reads the snapshots
```

Required repository secrets:
- `SERPAPI_KEY` — https://serpapi.com/manage-api-key
- `YOUTUBE_API_KEY` — Google Cloud project with YouTube Data API v3 enabled

Reddit uses the public JSON endpoints (no auth / no secret required), so
no Reddit credentials to manage.

Files:
- `config.py` — shared constants (topic list, timeframes)
- `app.py` — Streamlit dashboard, reads the three snapshots
- `scripts/fetch_trends.py` — SerpApi runner
- `scripts/fetch_reddit.py` — PRAW runner
- `scripts/fetch_youtube.py` — YouTube Data API runner
- `.github/workflows/refresh-*.yml` — three daily cron workflows + manual dispatch
- `requirements.txt` — runtime deps for Streamlit Cloud
- `requirements-fetch.txt` — deps shared across all fetch jobs

## Topics tracked

**Contaminants** — PFAS, forever chemicals, lead in water, arsenic in water,
nitrate in water, microplastics, fluoride in water, chromium 6

**Context / source** — well water testing, hard water, tap water safety,
bottled water

**Solutions** — water filter, water filtration, reverse osmosis, water
softener, whole house water filter

Edit `TOPIC_GROUPS` in `config.py` to change the list. After changing topics,
trigger the workflow manually from the Actions tab to refresh the snapshot.

## Run locally

Requires Python 3.11+ (3.12 recommended).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501.

## Refresh data locally (optional)

Export the relevant API credentials in your shell, then run any of the
fetch scripts:

```bash
source .venv/bin/activate
pip install -r requirements-fetch.txt

# Trends
export SERPAPI_KEY=your_key_here
python scripts/fetch_trends.py

# Reddit (no credentials needed)
python scripts/fetch_reddit.py

# YouTube
export YOUTUBE_API_KEY=...
python scripts/fetch_youtube.py
```

## Trigger a data refresh on GitHub

Go to the repo → **Actions** tab → **Refresh Google Trends data** →
**Run workflow**. Takes ~1 minute. The workflow commits the updated
`data/trends.json` and Streamlit Cloud auto-redeploys.

## Known quirks

- **Compare tab**: values are normalized within each 5-term pytrends batch,
  so cross-batch comparisons are approximate. Best for comparing trend
  *shape* and *timing* rather than absolute magnitude. If true
  cross-comparison matters, we can add anchor-based normalization as a
  follow-up.
- **SerpApi credits**: each trends run uses ~16 credits (4 timeframes × 4
  batches). Monthly cron usage is ~480 credits. The Developer plan (5k/mo) has
  plenty of headroom for manual re-runs.
- **Reddit search noise**: `r/all` search returns everything from product
  recommendations to jokes to unrelated meanings. If signal is poor, curate
  a subreddit whitelist in `scripts/fetch_reddit.py`.
- **YouTube quota**: each run uses ~1,720 of the daily 10k free quota. Room
  for 4–5 manual re-runs per day.
