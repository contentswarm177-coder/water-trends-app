"""Water Quality Trends Dashboard — US Google Trends for water-related topics."""
from __future__ import annotations

import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pytrends.request import TrendReq


TOPIC_GROUPS: dict[str, list[str]] = {
    "Contaminants": [
        "PFAS",
        "forever chemicals",
        "lead in water",
        "arsenic in water",
        "nitrate in water",
        "microplastics",
        "fluoride in water",
        "chromium 6",
    ],
    "Context / source": [
        "well water testing",
        "hard water",
        "tap water safety",
        "bottled water",
    ],
    "Solutions": [
        "water filter",
        "water filtration",
        "reverse osmosis",
        "water softener",
        "whole house water filter",
    ],
}

ALL_TOPICS: list[str] = [t for group in TOPIC_GROUPS.values() for t in group]

TIMEFRAMES = {
    "Last 3 months": "today 3-m",
    "Last 12 months": "today 12-m",
    "Last 2 years": "today 24-m",
    "Last 5 years": "today 5-y",
}

BATCH_SIZE = 5
BATCH_DELAY_SEC = 1.5
MAX_RETRIES = 3


def _fetch_batch(pytrends: TrendReq, batch: list[str], timeframe: str, geo: str) -> pd.DataFrame:
    for attempt in range(MAX_RETRIES):
        try:
            pytrends.build_payload(batch, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            return df.drop(columns=["isPartial"], errors="ignore")
        except Exception:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(2 ** attempt)
    return pd.DataFrame()


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_trends(topics: tuple[str, ...], timeframe: str, geo: str = "US") -> pd.DataFrame:
    pytrends = TrendReq(hl="en-US", tz=360)
    frames: list[pd.DataFrame] = []
    topics_list = list(topics)
    for i in range(0, len(topics_list), BATCH_SIZE):
        batch = topics_list[i : i + BATCH_SIZE]
        df = _fetch_batch(pytrends, batch, timeframe, geo)
        if not df.empty:
            frames.append(df)
        if i + BATCH_SIZE < len(topics_list):
            time.sleep(BATCH_DELAY_SEC)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, axis=1)


def sparkline(series: pd.Series, title: str) -> go.Figure:
    fig = px.area(series, height=170)
    fig.update_layout(
        title=dict(text=title, x=0.0, font=dict(size=14)),
        margin=dict(l=0, r=0, t=32, b=0),
        showlegend=False,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(range=[0, 100]),
    )
    fig.update_traces(hovertemplate="%{x|%b %d, %Y}<br>Interest: %{y}<extra></extra>")
    return fig


def overlay_chart(df: pd.DataFrame) -> go.Figure:
    fig = px.line(df, height=460)
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, title=None),
        xaxis_title=None,
        yaxis_title="Search interest (0–100)",
    )
    return fig


st.set_page_config(page_title="Water Quality Trends", layout="wide", page_icon="💧")

st.title("💧 Water Quality Trends")
st.caption(
    "US Google Trends for contaminants, water context, and filtration solutions. "
    "Data cached 24 hours."
)

with st.sidebar:
    st.header("Controls")
    timeframe_label = st.selectbox("Time range", list(TIMEFRAMES.keys()), index=1)
    timeframe = TIMEFRAMES[timeframe_label]
    st.divider()
    st.markdown("**Tracked topics**")
    for group, topics in TOPIC_GROUPS.items():
        with st.expander(group, expanded=False):
            for t in topics:
                st.markdown(f"- {t}")
    st.divider()
    st.caption(
        "Source: Google Trends via pytrends. Values are 0–100 relative to peak "
        "search interest within each pytrends request batch (max 5 terms per batch)."
    )

try:
    with st.spinner("Fetching Google Trends data (cached for 24h)…"):
        df = fetch_trends(tuple(ALL_TOPICS), timeframe)
except Exception as e:
    st.error(f"Google Trends request failed: {e}")
    st.info("Google Trends aggressively rate-limits. Try again in a few minutes.")
    st.stop()

if df.empty:
    st.error("No data returned from Google Trends. Likely rate-limited — try again shortly.")
    st.stop()

tab_overview, tab_compare, tab_data = st.tabs(["Overview", "Compare", "Data"])

with tab_overview:
    st.markdown(
        "Each chart shows search interest over time for one topic. "
        "Values are normalized 0–100 within each 5-term fetch batch — great for spotting "
        "trend shape and spikes, but use the **Compare** tab for apples-to-apples comparison."
    )
    for group, topics in TOPIC_GROUPS.items():
        st.subheader(group)
        cols = st.columns(4)
        for idx, topic in enumerate(topics):
            if topic not in df.columns:
                continue
            with cols[idx % 4]:
                st.plotly_chart(sparkline(df[topic], topic), use_container_width=True)

with tab_compare:
    st.markdown("Pick up to **5 topics** to overlay on one chart (true direct comparison).")
    selection = st.multiselect(
        "Topics",
        options=ALL_TOPICS,
        default=["PFAS", "microplastics", "lead in water"],
        max_selections=5,
    )
    if selection:
        with st.spinner("Fetching comparison data…"):
            cmp_df = fetch_trends(tuple(selection), timeframe)
        if not cmp_df.empty:
            st.plotly_chart(overlay_chart(cmp_df), use_container_width=True)
        else:
            st.info("No data returned for the selected topics.")
    else:
        st.info("Select at least one topic to compare.")

with tab_data:
    st.markdown("Raw interest-over-time data. Use the download button to export for other workflows.")
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV",
        data=df.to_csv().encode("utf-8"),
        file_name=f"water_trends_{timeframe.replace(' ', '_')}.csv",
        mime="text/csv",
    )
