#!/usr/bin/env python3
"""Analyst price-target screener.

Pulls consensus analyst targets and rating counts from Yahoo Finance (via the
unofficial yfinance library) and ranks tickers by potential upside:

    upside = (consensus target - current price) / current price

Usage:
    python screener.py AAPL MSFT NVDA
    python screener.py --file tickers.txt --target median --csv results.csv

Data is for personal use only; Yahoo's terms do not permit redistribution.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf


def fetch(symbol: str, target_kind: str) -> dict:
    ticker = yf.Ticker(symbol)
    row = {"Ticker": symbol}
    try:
        info = ticker.info or {}
    except Exception as exc:  # network errors, delisted tickers, rate limits
        row["Error"] = str(exc)[:60]
        return row

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    target = info.get(f"target{target_kind.capitalize()}Price")

    row.update(
        Name=(info.get("shortName") or "")[:24],
        Price=price,
        Target=target,
        Low=info.get("targetLowPrice"),
        High=info.get("targetHighPrice"),
        Upside=(target - price) / price if price and target else None,
        Analysts=info.get("numberOfAnalystOpinions"),
        Rating=info.get("recommendationKey"),
    )

    try:
        recs = ticker.recommendations
        if recs is not None and not recs.empty:
            current = recs[recs["period"] == "0m"].iloc[0]
            row["Buy"] = int(current["strongBuy"] + current["buy"])
            row["Hold"] = int(current["hold"])
            row["Sell"] = int(current["sell"] + current["strongSell"])
    except Exception:
        pass  # rating breakdown is optional

    return row


def load_tickers(args) -> list[str]:
    tickers = list(args.tickers)
    if args.file:
        with open(args.file) as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    tickers.extend(line.replace(",", " ").split())
    # de-duplicate, preserve order
    return list(dict.fromkeys(t.upper() for t in tickers))


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank stocks by analyst-target upside.")
    parser.add_argument("tickers", nargs="*", help="ticker symbols")
    parser.add_argument("-f", "--file", help="file with tickers (whitespace/comma separated, # comments)")
    parser.add_argument("-t", "--target", choices=["mean", "median"], default="mean",
                        help="consensus target to use (default: mean)")
    parser.add_argument("--min-analysts", type=int, default=0,
                        help="drop tickers covered by fewer analysts")
    parser.add_argument("--csv", help="also write results to this CSV path")
    args = parser.parse_args()

    tickers = load_tickers(args)
    if not tickers:
        parser.error("give tickers as arguments or with --file")

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda s: fetch(s, args.target), tickers))

    df = pd.DataFrame(rows)
    if "Analysts" in df and args.min_analysts:
        df = df[df["Analysts"].fillna(0) >= args.min_analysts]
    if "Upside" in df:
        df = df.sort_values("Upside", ascending=False, na_position="last")

    if args.csv:
        df.to_csv(args.csv, index=False)

    display = df.copy()
    for col in ("Price", "Target", "Low", "High"):
        if col in display:
            display[col] = display[col].map(lambda v: f"{v:,.2f}" if pd.notna(v) else "-")
    if "Upside" in display:
        display["Upside"] = display["Upside"].map(lambda v: f"{v:+.1%}" if pd.notna(v) else "-")
    for col in ("Analysts", "Buy", "Hold", "Sell"):
        if col in display:
            display[col] = display[col].map(lambda v: f"{int(v)}" if pd.notna(v) else "-")

    print(f"Consensus target: {args.target}")
    print(display.fillna("-").to_string(index=False))
    if args.csv:
        print(f"\nSaved {len(df)} rows to {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
