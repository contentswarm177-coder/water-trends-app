"""Water Quality Trends & Social Listening Dashboard.

Reads three snapshots committed by GitHub Actions workflows:
- data/trends.json            (Google Trends via SerpApi; manual-only refresh)
- data/youtube_mentions.json  (YouTube Data API v3; daily cron)
- data/news_mentions.json     (GDELT 2.0 news; daily cron)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import ALL_TOPICS, TIMEFRAMES, TOPIC_GROUPS

DATA_DIR = Path(__file__).parent / "data"
TRENDS_FILE = DATA_DIR / "trends.json"
YOUTUBE_FILE = DATA_DIR / "youtube_mentions.json"
NEWS_FILE = DATA_DIR / "news_mentions.json"


@st.cache_data(show_spinner=False)
def load_json(path_str: str) -> dict:
    path = Path(path_str)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def format_refreshed(iso: str | None) -> str:
    if not iso:
        return "never"
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")


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


def daily_volume_df(mentions: list[dict], date_field: str) -> pd.DataFrame:
    """Pivot mentions into a date-indexed DataFrame with one column per keyword."""
    rows: list[dict] = []
    for m in mentions:
        raw = m.get(date_field)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw, tz=timezone.utc).date()
        else:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        for kw in m.get("matched_keywords", []):
            rows.append({"date": pd.Timestamp(dt), "keyword": kw, "count": 1})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.groupby(["date", "keyword"])["count"].sum().unstack(fill_value=0).sort_index()


def volume_chart(df: pd.DataFrame, y_title: str) -> go.Figure:
    fig = px.bar(df, height=360, barmode="stack")
    fig.update_layout(
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, title=None),
        xaxis_title=None,
        yaxis_title=y_title,
    )
    return fig


st.set_page_config(page_title="Water Quality Trends", layout="wide", page_icon="💧")

trends = load_json(str(TRENDS_FILE))
youtube = load_json(str(YOUTUBE_FILE))
news = load_json(str(NEWS_FILE))

st.title("💧 Water Quality Trends")

if not trends:
    st.error("No trends snapshot found at `data/trends.json`.")
    st.info(
        "Refreshed daily by the **Refresh Google Trends data** GitHub Actions "
        "workflow. Trigger it manually if this is a fresh deploy."
    )
    st.stop()

trends_refreshed = format_refreshed(trends.get("refreshed_at"))
st.caption(
    f"**Trends:** {trends_refreshed} · "
    f"**YouTube:** {format_refreshed(youtube.get('refreshed_at'))} · "
    f"**News:** {format_refreshed(news.get('refreshed_at'))}"
)

with st.sidebar:
    st.header("Controls")
    timeframe_label = st.selectbox("Time range (Trends only)", list(TIMEFRAMES.keys()), index=1)
    timeframe = TIMEFRAMES[timeframe_label]
    st.divider()
    st.markdown("**Tracked topics**")
    for group, topics in TOPIC_GROUPS.items():
        with st.expander(group, expanded=False):
            for t in topics:
                st.markdown(f"- {t}")
    st.divider()
    st.caption(
        "Sources — Trends: SerpApi (Google Trends). "
        "YouTube: Data API v3, US + English, quoted-phrase + title filter. "
        "News: GDELT 2.0, US sources + English, quoted-phrase + title filter."
    )

df_trends = frame_for_timeframe(trends, timeframe)
if df_trends.empty:
    st.error(f"No trends data for timeframe `{timeframe}`.")
    st.stop()

tab_search, tab_news, tab_youtube, tab_data = st.tabs(
    ["Search Overview", "News", "YouTube", "Data"]
)

with tab_search:
    st.markdown(
        "Search interest over time for each topic. Great for spotting shape and spikes."
    )
    for group, topics in TOPIC_GROUPS.items():
        st.subheader(group)
        cols = st.columns(4)
        for idx, topic in enumerate(topics):
            if topic not in df_trends.columns:
                continue
            with cols[idx % 4]:
                st.plotly_chart(sparkline(df_trends[topic], topic), use_container_width=True)

with tab_news:
    if not news:
        st.warning("No news snapshot yet. Trigger the **Refresh news mentions** workflow.")
    else:
        mentions = news.get("mentions", [])
        st.markdown(
            f"{len(mentions):,} unique US/English news articles from the last "
            f"{news.get('timespan', '7d')} mentioning tracked topics (GDELT 2.0)."
        )
        kw_filter = st.multiselect(
            "Filter by keyword", ALL_TOPICS, default=[], key="news_kw"
        )
        filtered = [
            m for m in mentions
            if not kw_filter or any(k in m.get("matched_keywords", []) for k in kw_filter)
        ]

        col_chart, col_counts = st.columns([3, 1])
        with col_chart:
            vol_df = daily_volume_df(filtered, "published_at")
            if not vol_df.empty:
                st.plotly_chart(volume_chart(vol_df, "Articles per day"), use_container_width=True)
            else:
                st.info("No articles match the filter.")
        with col_counts:
            st.markdown("**Articles per keyword**")
            counts = (
                pd.Series(news.get("by_keyword_count", {}))
                .sort_values(ascending=False)
                .rename("count")
                .to_frame()
            )
            st.dataframe(counts, use_container_width=True, height=360)

        st.divider()
        st.subheader("Top domains")
        from collections import Counter
        domain_counts = Counter(m.get("domain") for m in filtered if m.get("domain"))
        if domain_counts:
            domain_df = pd.DataFrame(
                domain_counts.most_common(15), columns=["Domain", "Articles"]
            )
            st.dataframe(domain_df, hide_index=True, use_container_width=False)

        st.divider()
        st.subheader("Recent articles")
        top_n = st.slider("Articles to show", 5, 100, 30, key="news_topn")
        if filtered:
            articles_df = pd.DataFrame(filtered)
            articles_df["published"] = pd.to_datetime(
                articles_df["published_at"], utc=True, errors="coerce"
            )
            articles_df["matched_keywords"] = articles_df["matched_keywords"].apply(", ".join)
            articles_df = articles_df.head(top_n)
            st.dataframe(
                articles_df[
                    ["published", "domain", "title", "matched_keywords", "url"]
                ],
                column_config={
                    "published": st.column_config.DatetimeColumn("Published", format="MMM D, HH:mm"),
                    "domain": "Source",
                    "title": "Headline",
                    "matched_keywords": "Keywords",
                    "url": st.column_config.LinkColumn("Link", display_text="open"),
                },
                hide_index=True,
                use_container_width=True,
            )

with tab_youtube:
    if not youtube:
        st.warning("No YouTube snapshot yet. Trigger the **Refresh YouTube mentions** workflow.")
    else:
        mentions = youtube.get("mentions", [])
        st.markdown(
            f"{len(mentions):,} unique YouTube videos from the last "
            f"{youtube.get('days_back', 7)} days mentioning tracked topics."
        )
        kw_filter = st.multiselect(
            "Filter by keyword", ALL_TOPICS, default=[], key="yt_kw"
        )
        filtered = [
            m for m in mentions
            if not kw_filter or any(k in m.get("matched_keywords", []) for k in kw_filter)
        ]

        col_chart, col_counts = st.columns([3, 1])
        with col_chart:
            vol_df = daily_volume_df(filtered, "published_at")
            if not vol_df.empty:
                st.plotly_chart(volume_chart(vol_df, "Videos per day"), use_container_width=True)
            else:
                st.info("No videos match the filter.")
        with col_counts:
            st.markdown("**Videos per keyword**")
            counts = (
                pd.Series(youtube.get("by_keyword_count", {}))
                .sort_values(ascending=False)
                .rename("count")
                .to_frame()
            )
            st.dataframe(counts, use_container_width=True, height=360)

        st.divider()
        st.subheader("Top videos")
        sort_by = st.radio(
            "Sort by", ["view_count", "like_count", "comment_count"],
            horizontal=True, key="yt_sort",
        )
        top_n = st.slider("Videos to show", 5, 50, 20, key="yt_topn")
        if filtered:
            videos_df = pd.DataFrame(filtered)
            videos_df["published"] = pd.to_datetime(videos_df["published_at"], utc=True)
            videos_df["matched_keywords"] = videos_df["matched_keywords"].apply(", ".join)
            videos_df = videos_df.sort_values(sort_by, ascending=False, na_position="last").head(top_n)
            st.dataframe(
                videos_df[
                    ["thumbnail", "published", "channel_title", "title",
                     "view_count", "like_count", "comment_count",
                     "matched_keywords", "url"]
                ],
                column_config={
                    "thumbnail": st.column_config.ImageColumn("Thumb"),
                    "published": st.column_config.DatetimeColumn("Published", format="MMM D"),
                    "channel_title": "Channel",
                    "title": "Title",
                    "view_count": st.column_config.NumberColumn("Views"),
                    "like_count": st.column_config.NumberColumn("Likes"),
                    "comment_count": st.column_config.NumberColumn("Comments"),
                    "matched_keywords": "Keywords",
                    "url": st.column_config.LinkColumn("Link", display_text="open"),
                },
                hide_index=True,
                use_container_width=True,
            )

with tab_data:
    st.markdown("Raw trends data for the selected timeframe. Download for downstream use.")
    st.dataframe(df_trends, use_container_width=True)
    st.download_button(
        "Download trends CSV",
        data=df_trends.to_csv().encode("utf-8"),
        file_name=f"water_trends_{timeframe.replace(' ', '_')}.csv",
        mime="text/csv",
    )
    if news:
        st.divider()
        st.markdown(f"**News mentions JSON** · {news.get('total_unique_mentions', 0)} articles")
        st.download_button(
            "Download News JSON",
            data=json.dumps(news, indent=2).encode("utf-8"),
            file_name="news_mentions.json",
            mime="application/json",
        )
    if youtube:
        st.divider()
        st.markdown(f"**YouTube mentions JSON** · {youtube.get('total_unique_mentions', 0)} videos")
        st.download_button(
            "Download YouTube JSON",
            data=json.dumps(youtube, indent=2).encode("utf-8"),
            file_name="youtube_mentions.json",
            mime="application/json",
        )
