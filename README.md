# Water Quality Trends

A public Streamlit dashboard tracking US Google Trends search interest for
water quality topics (contaminants, filtration, water context).

## Architecture

Google Trends has no official API and the community pytrends scraper is
rate-limited into oblivion in 2026. We use **SerpApi's Google Trends engine**
to fetch data via a daily GitHub Actions workflow that commits the snapshot
back to the repo:

```
GitHub Actions (cron 06:00 UTC)
      │
      │ SerpApi Google Trends (using SERPAPI_KEY secret)
      ▼
  data/trends.json  ──►  commit to main
      │
      ▼
Streamlit Cloud (auto-redeploys on push) reads the JSON
```

The SerpApi key is stored as the `SERPAPI_KEY` repository secret.

Files:
- `config.py` — shared constants (topic list, timeframes)
- `app.py` — Streamlit dashboard, reads `data/trends.json`
- `scripts/fetch_trends.py` — SerpApi runner, writes `data/trends.json`
- `.github/workflows/refresh-trends.yml` — daily cron + manual dispatch
- `requirements.txt` — runtime deps for Streamlit Cloud
- `requirements-fetch.txt` — deps for the fetch job (requests + pandas)

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

Requires a SerpApi key exported in your shell:

```bash
export SERPAPI_KEY=your_key_here
source .venv/bin/activate
pip install -r requirements-fetch.txt
python scripts/fetch_trends.py
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
- **SerpApi credits**: each workflow run uses ~16 credits (4 timeframes × 4
  batches). Monthly cron usage is ~480 credits. The Developer plan (5k/mo) has
  plenty of headroom for manual re-runs.
