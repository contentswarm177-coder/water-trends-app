# Water Quality Trends

A public Streamlit dashboard tracking US Google Trends search interest for
water quality topics (contaminants, filtration, water context).

## Architecture

Two independent GitHub Actions workflows fetch from different sources and
commit JSON snapshots to the repo. The Streamlit app reads the committed
files — no live API calls at view time.

```
GitHub Actions
  ├─ manual-only  SerpApi Google Trends    →  data/trends.json
  └─ 09:00 UTC    YouTube Data API v3      →  data/youtube_mentions.json
      │
      │ commits to main
      ▼
  Streamlit Cloud auto-redeploys, reads the snapshots
```

Reddit was scoped out of v1: Reddit's new developer policy blocks
script-app creation for most users, and unauthenticated public-JSON
requests are IP-blocked from GitHub Actions runners. Revisit via a paid
scraper (Apify, ~$30–50/mo) if Reddit coverage becomes a priority.

**Why trends is manual-only:** SerpApi's free tier is 100 searches/month; a
daily cron would burn ~480. Trigger the `Refresh Google Trends data` workflow
manually when you want fresh trend data (uses ~16 credits per run, so ~5-6
manual refreshes/month fit in the free tier). Re-enable the daily schedule
in `.github/workflows/refresh-trends.yml` once on a paid SerpApi plan.

Required repository secrets:
- `SERPAPI_KEY` — https://serpapi.com/manage-api-key
- `YOUTUBE_API_KEY` — Google Cloud project with YouTube Data API v3 enabled

Reddit uses the public JSON endpoints (no auth / no secret required), so
no Reddit credentials to manage.

Files:
- `config.py` — shared constants (topic list, timeframes)
- `app.py` — Streamlit dashboard, reads the two snapshots
- `scripts/fetch_trends.py` — SerpApi runner
- `scripts/fetch_youtube.py` — YouTube Data API runner
- `.github/workflows/refresh-*.yml` — trends (manual) + youtube (daily cron)
- `requirements.txt` — runtime deps for Streamlit Cloud
- `requirements-fetch.txt` — deps shared across fetch jobs

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
- **YouTube quota**: each run uses ~1,720 of the daily 10k free quota. Room
  for 4–5 manual re-runs per day.
- **YouTube signal**: search uses quoted phrases + a post-fetch filter that
  drops videos whose title or description don't contain a matched keyword.
  Cuts noise (random viral shorts) substantially but may still surface
  off-topic content with keyword-shaped titles — curate via the dashboard.
