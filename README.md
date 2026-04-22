# Water Quality Trends

A public Streamlit dashboard tracking US Google Trends search interest for
water quality topics (contaminants, filtration, water context).

## Architecture

Google Trends rate-limits aggressively on shared IPs like Streamlit Cloud's.
To sidestep that, the dashboard reads from a **committed data snapshot** that
is refreshed daily by GitHub Actions:

```
GitHub Actions (cron 06:00 UTC)
      │
      │ pytrends fetch
      ▼
  data/trends.json  ──►  commit to main
      │
      ▼
Streamlit Cloud (auto-redeploys on push) reads the JSON
```

Files:
- `config.py` — shared constants (topic list, timeframes)
- `app.py` — Streamlit dashboard, reads `data/trends.json`
- `scripts/fetch_trends.py` — pytrends runner, writes `data/trends.json`
- `.github/workflows/refresh-trends.yml` — daily cron + manual dispatch
- `requirements.txt` — runtime deps for Streamlit Cloud (no pytrends)
- `requirements-fetch.txt` — deps for the fetch job

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

```bash
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
- **pytrends reliability**: GitHub Actions runners rotate IPs, so rate-limit
  hits are rare but possible. If a refresh fails, re-run the workflow.
