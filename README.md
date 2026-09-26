# price-target-screener

Rank stocks by how far their current price sits below (or above) the Wall Street consensus price target.

```
upside = (consensus target − current price) / current price
```

It comes in two forms:

- **Dashboard** (`app.py`): a Streamlit page with a sortable table, charts, and recent analyst actions per ticker.
- **Command-line screener** (`screener.py`): prints the same table in the terminal and can save it as CSV.

Data comes from Yahoo Finance via the unofficial [`yfinance`](https://github.com/ranaroussi/yfinance) library. Individual analyst names come from [Financial Modeling Prep](https://site.financialmodelingprep.com/) (optional, needs a free API key).

> **Personal use only.** Yahoo's and FMP's terms don't allow redistributing their data. Don't host this publicly without a proper data license.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the dashboard

```bash
streamlit run app.py
```

It opens at http://localhost:8501.

### What's on the page

| Section | What it shows |
|---|---|
| **Sidebar** | Edit tickers, switch between mean and median consensus target, set a minimum analyst count, refresh data |
| **Summary** | Tickers shown, top upside, median upside, how many trade below their target |
| **Table** | Price, consensus target, upside %, target low/high, analyst count, consensus rating, Buy/Hold/Sell counts |
| **Potential upside** | Upside per ticker (green = below target, red = above) |
| **Target range vs. price** | Lowest to highest analyst target, with the consensus marked |
| **Rating mix** | Share of Buy / Hold / Sell ratings per ticker |
| **Recent analyst actions** | Per ticker: each firm's latest rating and target change, plus named analysts if FMP is set up |
| **Download CSV** | Exports the current table |

Data is cached for an hour. Use **Refresh data** in the sidebar to fetch fresh numbers.

## Run the command-line screener

```bash
# tickers as arguments
python screener.py AAPL MSFT NVDA

# tickers from the watchlist file
python screener.py -f tickers.txt

# median target, at least 10 analysts, save to CSV
python screener.py -f tickers.txt --target median --min-analysts 10 --csv results.csv
```

| Option | Meaning |
|---|---|
| `-f, --file` | Read tickers from a file |
| `-t, --target` | `mean` (default) or `median` consensus target |
| `--min-analysts N` | Skip tickers covered by fewer than N analysts |
| `--csv PATH` | Also save results to a CSV file |

## Watchlist

Edit `tickers.txt` to change the default tickers for both tools. Put one or more tickers per line, separated by spaces or commas. Lines starting with `#` are ignored.

```
# Big tech
AAPL MSFT NVDA GOOGL AMZN
META TSLA AMD
```

## Optional: individual analyst names (FMP)

Yahoo only reports the brokerage firm (e.g. "JP Morgan"), not the analyst. To see names:

1. Create a free API key at [financialmodelingprep.com](https://site.financialmodelingprep.com/developer/docs).
2. Copy the template and paste your key in:
   ```bash
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   ```
   ```toml
   FMP_API_KEY = "your-key-here"
   ```
   Or set the environment variable instead: `export FMP_API_KEY=your-key-here`
3. Reload the dashboard and open the **By analyst (FMP)** tab under *Recent analyst actions*.

`.streamlit/secrets.toml` is in `.gitignore`, so the key never gets committed.

If the tab shows an error saying the endpoint isn't available on your plan, FMP has put that endpoint behind a paid tier.

## Notes and limitations

- **Analyst counts don't always add up.** The *Analysts* column is the number of price targets. The Buy/Hold/Sell counts come from a separate Yahoo dataset and can be smaller.
- **yfinance is unofficial.** It scrapes Yahoo Finance, so a change on Yahoo's side can break it. If data stops loading, try `pip install -U yfinance`.
- **Invalid or delisted tickers** show as a warning on the dashboard, or as an empty row in the terminal.
- **This is not investment advice.** Consensus targets are often wrong and tend to lag the price.

## Files

```
app.py                          Streamlit dashboard
screener.py                     Command-line screener and shared data fetching
tickers.txt                     Default watchlist
requirements.txt                Python dependencies
.streamlit/secrets.toml.example Template for the optional FMP API key
.gitignore                      Keeps secrets, caches and CSV exports out of git
```
