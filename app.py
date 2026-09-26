"""Streamlit dashboard for analyst price-target upside.

Run with:  streamlit run app.py
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from screener import fetch

WATCHLIST = Path(__file__).with_name("tickers.txt")
POSITIVE, NEGATIVE, NEUTRAL = "#2E9E5B", "#D1495B", "#8A8F98"


def default_tickers() -> str:
    if not WATCHLIST.exists():
        return "AAPL MSFT NVDA"
    lines = (line.split("#")[0].strip() for line in WATCHLIST.read_text().splitlines())
    return " ".join(line for line in lines if line)


def parse_tickers(text: str) -> list[str]:
    return list(dict.fromkeys(t.upper() for t in text.replace(",", " ").split()))


@st.cache_data(ttl=3600, show_spinner=False)
def load(tickers: tuple[str, ...], target_kind: str) -> pd.DataFrame:
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda s: fetch(s, target_kind), tickers))
    return pd.DataFrame(rows)


ACTION_LABELS = {"up": "Upgrade", "down": "Downgrade", "init": "Initiated",
                 "main": "Maintained", "reit": "Reiterated"}


@st.cache_data(ttl=3600, show_spinner=False)
def firm_actions(symbol: str) -> pd.DataFrame:
    """Rating and price-target changes by brokerage firm, newest first."""
    try:
        raw = yf.Ticker(symbol).upgrades_downgrades
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()

    raw = raw.reset_index()
    target = raw.get("currentPriceTarget")
    prior = raw.get("priorPriceTarget")
    out = pd.DataFrame({
        "Date": pd.to_datetime(raw["GradeDate"]).dt.tz_localize(None),
        "Firm": raw["Firm"],
        "Rating": raw["ToGrade"],
        "Previous rating": raw["FromGrade"].replace("", None),
        "Rating action": raw["Action"].map(ACTION_LABELS).fillna(raw["Action"]),
        "Target action": raw.get("priceTargetAction"),
        "Target": target.where(target > 0) if target is not None else None,
        "Prior": prior.where(prior > 0) if prior is not None else None,
    })
    out["Change"] = (out["Target"] / out["Prior"] - 1) * 100
    return out.sort_values("Date", ascending=False).reset_index(drop=True)


def fmp_key() -> str | None:
    try:
        key = st.secrets.get("FMP_API_KEY")
    except Exception:  # no secrets.toml
        key = None
    return key or os.environ.get("FMP_API_KEY")


@st.cache_data(ttl=3600, show_spinner=False)
def fmp_price_targets(symbol: str, key: str) -> pd.DataFrame:
    """Individual analyst price targets from Financial Modeling Prep."""
    try:
        resp = requests.get(
            "https://financialmodelingprep.com/stable/price-target-news",
            params={"symbol": symbol, "limit": 100, "apikey": key},
            timeout=15,
        )
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
    if isinstance(data, dict):  # FMP returns {"Error Message": ...} on bad key / plan limits
        raise RuntimeError(data.get("Error Message") or str(data))
    if not data:
        return pd.DataFrame()

    raw = pd.DataFrame(data)
    col = lambda name: raw[name] if name in raw else None
    out = pd.DataFrame({
        "Date": pd.to_datetime(col("publishedDate"), utc=True).dt.tz_localize(None),
        "Analyst": col("analystName"),
        "Firm": col("analystCompany"),
        "Target": col("priceTarget"),
        "Price then": col("priceWhenPosted"),
        "Headline": col("newsTitle"),
        "Link": col("newsURL"),
    })
    out["Implied upside"] = (out["Target"] / out["Price then"] - 1) * 100
    return out.sort_values("Date", ascending=False).reset_index(drop=True)


st.set_page_config(page_title="Analyst Upside", page_icon="📈", layout="wide")
st.title("Analyst Upside Screener")
st.caption("Consensus analyst price targets from Yahoo Finance via yfinance. Personal use only.")

with st.sidebar:
    st.header("Watchlist")
    ticker_text = st.text_area("Tickers", default_tickers(), height=120,
                               help="Separate with spaces, commas or new lines.")
    target_kind = st.radio("Consensus target", ["mean", "median"], horizontal=True)
    min_analysts = st.slider("Minimum analysts", 0, 50, 0)
    if st.button("Refresh data", width="stretch"):
        load.clear()
    st.caption("Data is cached for an hour.")

tickers = parse_tickers(ticker_text)
if not tickers:
    st.info("Add at least one ticker in the sidebar.")
    st.stop()

with st.spinner(f"Fetching {len(tickers)} tickers…"):
    raw = load(tuple(tickers), target_kind)

failed = raw[raw["Price"].isna()]["Ticker"].tolist() if "Price" in raw else raw["Ticker"].tolist()
df = raw.dropna(subset=["Price"]) if "Price" in raw else raw.iloc[0:0]
if "Analysts" in df:
    df = df[df["Analysts"].fillna(0) >= min_analysts]
df = df.sort_values("Upside", ascending=False, na_position="last").reset_index(drop=True)

if failed:
    st.warning(f"No data for: {', '.join(failed)}")
if df.empty:
    st.info("No tickers match the current filters.")
    st.stop()

# --- Summary metrics -------------------------------------------------------
ranked = df.dropna(subset=["Upside"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tickers shown", len(df))
if not ranked.empty:
    top = ranked.iloc[0]
    c2.metric("Top upside", top["Ticker"], f"{top['Upside']:+.1%}")
    c3.metric("Median upside", f"{ranked['Upside'].median():+.1%}")
    c4.metric("Below target", f"{(ranked['Upside'] > 0).sum()} / {len(ranked)}")

# --- Table -----------------------------------------------------------------
table = df.copy()
table["Upside"] = table["Upside"] * 100
st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    column_order=["Ticker", "Name", "Price", "Target", "Upside", "Low", "High",
                  "Analysts", "Rating", "Buy", "Hold", "Sell"],
    column_config={
        "Price": st.column_config.NumberColumn(format="$%.2f"),
        "Target": st.column_config.NumberColumn(f"Target ({target_kind})", format="$%.2f"),
        "Low": st.column_config.NumberColumn("Target low", format="$%.2f"),
        "High": st.column_config.NumberColumn("Target high", format="$%.2f"),
        "Upside": st.column_config.NumberColumn("Upside", format="%+.1f%%"),
        "Analysts": st.column_config.NumberColumn(help="Analysts with a price target"),
        "Rating": st.column_config.TextColumn("Consensus"),
        "Buy": st.column_config.NumberColumn(help="Strong buy + buy (current month)"),
        "Sell": st.column_config.NumberColumn(help="Sell + strong sell (current month)"),
    },
)

# --- Charts ----------------------------------------------------------------
left, right = st.columns(2)
order = ranked["Ticker"].tolist()

with left:
    st.subheader("Potential upside")
    bars = (
        alt.Chart(ranked)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            y=alt.Y("Ticker:N", sort=order, title=None),
            x=alt.X("Upside:Q", axis=alt.Axis(format="%"), title="Upside to consensus target"),
            color=alt.condition("datum.Upside >= 0", alt.value(POSITIVE), alt.value(NEGATIVE)),
            tooltip=["Ticker", "Name", alt.Tooltip("Upside:Q", format="+.1%"),
                     alt.Tooltip("Price:Q", format="$,.2f"), alt.Tooltip("Target:Q", format="$,.2f")],
        )
    )
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=NEUTRAL).encode(x="x:Q")
    st.altair_chart(bars + zero, width="stretch")

with right:
    st.subheader("Target range vs. price")
    ranges = ranked.dropna(subset=["Low", "High"]).assign(
        LowPct=lambda d: d["Low"] / d["Price"] - 1,
        HighPct=lambda d: d["High"] / d["Price"] - 1,
    )
    base = alt.Chart(ranges).encode(y=alt.Y("Ticker:N", sort=order, title=None))
    span = base.mark_rule(strokeWidth=6, opacity=0.35, color=NEUTRAL).encode(
        x=alt.X("LowPct:Q", axis=alt.Axis(format="%"), title="Target vs. current price (0% = price)"),
        x2="HighPct:Q",
        tooltip=["Ticker", alt.Tooltip("Low:Q", format="$,.2f"), alt.Tooltip("High:Q", format="$,.2f")],
    )
    point = base.mark_point(filled=True, size=90).encode(
        x="Upside:Q",
        color=alt.condition("datum.Upside >= 0", alt.value(POSITIVE), alt.value(NEGATIVE)),
        tooltip=["Ticker", alt.Tooltip("Target:Q", format="$,.2f"), alt.Tooltip("Upside:Q", format="+.1%")],
    )
    st.altair_chart(span + point + zero, width="stretch")
    st.caption("Grey bar: lowest to highest analyst target. Dot: consensus target.")

# --- Rating mix ------------------------------------------------------------
if {"Buy", "Hold", "Sell"} <= set(df.columns):
    st.subheader("Rating mix")
    mix = df.dropna(subset=["Buy"]).melt(
        id_vars="Ticker", value_vars=["Buy", "Hold", "Sell"], var_name="Rating", value_name="Count"
    )
    st.altair_chart(
        alt.Chart(mix)
        .mark_bar()
        .encode(
            y=alt.Y("Ticker:N", sort=order, title=None),
            x=alt.X("Count:Q", stack="normalize", axis=alt.Axis(format="%"), title="Share of ratings"),
            color=alt.Color("Rating:N", sort=["Buy", "Hold", "Sell"],
                            scale=alt.Scale(domain=["Buy", "Hold", "Sell"],
                                            range=[POSITIVE, NEUTRAL, NEGATIVE])),
            order=alt.Order("RatingOrder:Q"),
            tooltip=["Ticker", "Rating", "Count"],
        )
        .transform_calculate(RatingOrder="indexof(['Buy','Hold','Sell'], datum.Rating)"),
        width="stretch",
    )

st.download_button("Download CSV", df.to_csv(index=False), "analyst_upside.csv", "text/csv")

# --- Recent analyst actions -----------------------------------------------
st.divider()
st.subheader("Recent analyst actions")
pick_col, days_col = st.columns([1, 2])
symbol = pick_col.selectbox("Ticker", df["Ticker"].tolist())
days = days_col.slider("Look back (days)", 30, 365, 180, step=15)

tab_firms, tab_named = st.tabs(["By firm (Yahoo)", "By analyst (FMP)"])

with tab_firms:
    actions = firm_actions(symbol)
    if actions.empty:
        st.info(f"No rating actions available for {symbol}.")
    else:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        recent = actions[actions["Date"] >= cutoff]
        latest = recent.drop_duplicates("Firm")  # newest action per firm

        m1, m2, m3 = st.columns(3)
        m1.metric("Actions", len(recent))
        m2.metric("Firms", latest["Firm"].nunique())
        m3.metric("Target raises / cuts",
                  f"{(recent['Target action'] == 'Raises').sum()} / {(recent['Target action'] == 'Lowers').sum()}")

        show_all = st.toggle("Show every action (default: latest per firm)")
        st.dataframe(
            recent if show_all else latest,
            hide_index=True,
            width="stretch",
            column_order=["Date", "Firm", "Rating", "Target", "Change", "Target action",
                          "Prior", "Previous rating", "Rating action"],
            column_config={
                "Date": st.column_config.DateColumn(format="MMM D, YYYY"),
                "Target": st.column_config.NumberColumn(format="$%.2f"),
                "Prior": st.column_config.NumberColumn("Prior target", format="$%.2f"),
                "Change": st.column_config.NumberColumn(format="%+.1f%%"),
            },
        )
        st.caption("Yahoo lists the brokerage firm only, not the individual analyst.")

with tab_named:
    key = fmp_key()
    if not key:
        st.info(
            "Add a free Financial Modeling Prep API key to see individual analyst names. "
            "Put `FMP_API_KEY = \"...\"` in `.streamlit/secrets.toml` "
            "(or set the `FMP_API_KEY` environment variable) and reload."
        )
    else:
        try:
            named = fmp_price_targets(symbol, key)
        except RuntimeError as exc:
            st.error(f"FMP request failed: {exc}")
        else:
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
            named = named[named["Date"] >= cutoff] if not named.empty else named
            if named.empty:
                st.info(f"No named price targets for {symbol} in this window.")
            else:
                st.dataframe(
                    named,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Date": st.column_config.DateColumn(format="MMM D, YYYY"),
                        "Target": st.column_config.NumberColumn(format="$%.2f"),
                        "Price then": st.column_config.NumberColumn(format="$%.2f"),
                        "Implied upside": st.column_config.NumberColumn(format="%+.1f%%"),
                        "Link": st.column_config.LinkColumn(display_text="source"),
                    },
                )
