"""Water Quality Trends Dashboard — reads a daily snapshot from data/trends.json."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import ALL_TOPICS, TIMEFRAMES, TOPIC_GROUPS

DATA_FILE = Path(__file__).parent / "data" / "trends.json"


@st.cache_data(show_spinner=False)
def load_snapshot() -> dict:
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def frame_for_timeframe(snapshot: dict, timeframe: str) -> pd.DataFrame:
    tf = snapshot.get("timeframes", {}).get(timeframe)
    if not tf:
        return pd.DataFrame()
    return pd.DataFrame(tf["series"], index=pd.to_datetime(tf["dates"]))


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

snapshot = load_snapshot()

st.title("💧 Water Quality Trends")

if not snapshot:
    st.error("No data snapshot found.")
    st.info(
        "This dashboard reads from `data/trends.json`, refreshed daily by a GitHub "
        "Actions workflow. If this is a fresh deploy, the first refresh may still "
        "be pending — trigger the workflow manually from the Actions tab."
    )
    st.stop()

refreshed = datetime.fromisoformat(snapshot["refreshed_at"]).strftime("%Y-%m-%d %H:%M UTC")
st.caption(f"US Google Trends · snapshot refreshed {refreshed}")

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
        "search interest within each 5-term fetch batch. Use the Compare tab for "
        "grouped comparisons — values across batches are approximate."
    )

df = frame_for_timeframe(snapshot, timeframe)
if df.empty:
    st.error(f"No data for timeframe `{timeframe}` in the snapshot.")
    st.stop()

tab_overview, tab_compare, tab_data = st.tabs(["Overview", "Compare", "Data"])

with tab_overview:
    st.markdown(
        "Each chart shows search interest over time for one topic. "
        "Great for spotting shape and spikes."
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
    st.markdown(
        "Overlay multiple topics. **Note:** values are normalized within the "
        "original fetch batches (5 terms each), so cross-batch comparisons are "
        "approximate — best for comparing trend shape and timing rather than "
        "absolute magnitude."
    )
    selection = st.multiselect(
        "Topics",
        options=ALL_TOPICS,
        default=["PFAS", "microplastics", "lead in water"],
    )
    if selection:
        st.plotly_chart(overlay_chart(df[selection]), use_container_width=True)
    else:
        st.info("Select at least one topic to compare.")

with tab_data:
    st.markdown("Raw interest-over-time data. Download for downstream use.")
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV",
        data=df.to_csv().encode("utf-8"),
        file_name=f"water_trends_{timeframe.replace(' ', '_')}.csv",
        mime="text/csv",
    )
