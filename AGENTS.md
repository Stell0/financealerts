# Repository guidance

## Project and layout

FinanceAlerts is a Python command-line application that downloads Yahoo Finance
prices, calculates technical indicators, and reports BUY/SELL signals. Telegram
delivery is optional. There is no web service or packaged Python application.

- `src/main.py`: CLI entry point, ticker selection, indicator orchestration,
  current-day signal filtering, and Telegram MarkdownV2 report formatting.
- `src/yahoo_finance_api.py`: Yahoo Finance downloads and daily CSV cache handling;
  also contains hourly-price and earnings-date helpers.
- `src/indicators.py`: TA-Lib calculations that add columns to pandas DataFrames.
- `src/signals.py`: rules that accumulate numeric `signal` values and comma-ended
  `reason` strings on those DataFrames.
- `src/telegram_alert.py`: prints reports and optionally sends them using the
  asynchronous Telegram API.
- `data/*.csv`: tracked price caches, not disposable build output.
- `requirements.txt`: runtime dependencies; most are pinned, but `yfinance` is not.
- `Dockerfile`: Python 3.12 image, native TA-Lib build, and application startup.
- `.github/workflows/`: image builds, PR image builds, and scheduled execution
  with cache commits.

Local environments (`.venv/`, `fin/`), bytecode, scratch scripts, and debug CSVs
may exist outside tracked source. Check `git status --short` before editing and
preserve unrelated local work. The tracked implementation of `load_tickers` is
inside `src/main.py`; the local `src/load_tickers.py` is currently empty.

## Setup and execution

Run from the repository root: cache paths are relative to the working directory,
and `data/` must exist. Modules use sibling imports from `src/`.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use an existing environment if appropriate. Installing the pinned `TA-Lib`
Python binding requires native TA-Lib; the Dockerfile builds version 0.4.0 under
`/usr` before installing Python dependencies. Consult that recipe when local
installation fails.

```sh
# One ticker; the first positional argument overrides TICKER_LIST.
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID .venv/bin/python src/main.py INTC

# Multiple whitespace-separated tickers.
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID TICKER_LIST="TSLA INTC" \
  .venv/bin/python src/main.py

# Build and run locally when Docker is available.
docker build -t financealerts:local .
docker run --rm -e TICKER_LIST="TSLA INTC" financealerts:local
```

These runs access Yahoo Finance and can update caches (inside the container for
the Docker example). They are integration checks, not offline tests.

## Configuration and behavior to preserve

- The universe is merged from `config/tickers.txt`, `TICKER_LIST` and PaperTrader
  securities. A positional ticker overrides the scan only. Identity and assessment
  ingestion lives in `registry.py` and `papertrader_data.py`; never use PaperTrader
  prices or indicators. Preserve the GOOG/GOOGL and BTCUSD alias rules.
- `INDICATORS` is checked using substring membership for `RSI`, `SMA`, `MACD`,
  and `BB`. With it unset, RSI rules run by default. Moving-average crossover
  rules always run, and all indicator columns are calculated regardless of
  selected signal rules.
- The column named `SMA50` is currently computed with a 40-period window.
  Treat this as existing behavior; change it only when relevant to the task.
- `RSI_upper`, `RSI_lower`, `RSI_upper2`, and `RSI_lower2` configure RSI signal
  thresholds (defaults: 70, 30, 80, 20). Period environment variables declared
  in `indicators.py` are not wired into its function defaults or main's calls.
- Reports use only the last row when its date equals today's UTC date. Positive
  scores mean BUY; negative scores mean SELL. Preserve MarkdownV2 escaping and
  ticker-specific TradingView links when changing report formatting.
- Telegram credentials are read at module import. Reports are always printed;
  delivery occurs when both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set.
- The application does not automatically load `.env`. Keep credentials out of
  source, logs, documentation, and commits. Unset Telegram variables for local
  checks that should only print reports.

## Data and code changes

Keep downloads/cache normalization, indicator calculations, signal rules, and
message delivery in their existing modules. Follow nearby formatting; the
repository currently mixes tabs and spaces across functions, so avoid broad
formatting changes.

Daily caches use a date index and flat OHLCV columns. Yahoo Finance can return
MultiIndex columns, which the downloader flattens before saving. Existing cache
updates drop the last cached row, fetch overlapping dates, and deduplicate dates
keeping the newest values. Preserve these contracts when changing retrieval.
Use temporary directories and mocked downloads for cache tests so tracked price
history stays untouched. Review any `data/` diff separately from code changes.

## Verification

Run the tracked offline suite with `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
There is no configured lint/type-check tool.
For a quick syntax check without importing modules or writing bytecode:

```sh
python3 - <<'PY'
import ast
from pathlib import Path
for path in sorted(Path("src").glob("*.py")):
    ast.parse(path.read_text(), filename=str(path))
print("Python syntax OK")
PY
```

For behavior changes, use focused offline checks against the actual functions:
synthetic DataFrames for indicator/signal rules, mocked `yf.download` plus
temporary CSVs for cache behavior, and mocked Telegram delivery for reports.
Set `PYTHONPATH=src` when importing sibling modules from root-level checks.

The local untracked `src/test_cache.py` is an ad hoc validator, not a reliable
test gate: it copies the sanitization implementation, mixes root-relative
`data/` paths with `../.github/...`, and does not return a failing process exit
status when checks fail. `verify_fix.py` is currently empty. Do not report these
as a passing regression suite.

CI primarily builds and runs Docker images; it does not run a separate unit
suite. Both image-build workflows publish images, and the scheduled workflow
runs daily at `19:19` UTC, mounts the checkout, and commits cache changes. Inspect
these effects before using workflow dispatch as validation. For documentation
changes, checking content, paths, and the diff is sufficient. Report what was
actually checked and any checks that could not run.
