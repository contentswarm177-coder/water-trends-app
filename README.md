# Water Quality Trends

A public Streamlit dashboard tracking US Google Trends search interest for water
quality topics (contaminants, filtration, water context). Built as a lightweight
monitoring tool.

## Topics tracked

**Contaminants** — PFAS, forever chemicals, lead in water, arsenic in water,
nitrate in water, microplastics, fluoride in water, chromium 6

**Context / source** — well water testing, hard water, tap water safety,
bottled water

**Solutions** — water filter, water filtration, reverse osmosis, water softener,
whole house water filter

Edit `TOPIC_GROUPS` at the top of `app.py` to change the list.

## Run locally

Requires Python 3.11+ (3.12 recommended).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501.

## Deploy to Streamlit Community Cloud

One-time setup:

```bash
# from the project root
git init
git add .
git commit -m "Initial commit: water trends dashboard"

# create the repo on GitHub (requires gh CLI, or do it manually on github.com)
gh repo create water-trends-app --public --source=. --remote=origin --push
```

Then:

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **New app** → pick your repo → branch `main` → main file `app.py`.
3. Deploy. You'll get a public URL like `https://water-trends-app.streamlit.app`.

Pushes to `main` auto-redeploy.

## Data layer

Trends data is fetched via `pytrends` and cached 24 hours with `@st.cache_data`.
The **Data** tab exposes the raw DataFrame as a CSV download, so other
workflows (e.g. content pipelines) can consume the same numbers.

## Known quirks

- **Google Trends rate limits**: `pytrends` is unofficial. 429 errors happen,
  especially on Streamlit Cloud's shared IPs. The 24h cache absorbs most of
  this — first load after cache expiry is the only risk window.
- **Batch normalization**: pytrends caps comparisons at 5 terms per request.
  17 topics → 4 sequential batches. Values within a batch are directly
  comparable; across batches they aren't. The **Compare** tab sidesteps this
  by fetching the user's selection as a single batch.
