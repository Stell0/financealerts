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
Python binding now uses a pinned wheel with its native library included. The
Dockerfile installs the small pinned runtime set on Python 3.12-slim.

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
- RSI alone triggers candidates, inclusively at RSI_lower (30) and RSI_upper (70).
  `INDICATORS` no longer selects independent triggers. Ratings use defaults in
  `rating_config.py`; `ratings.py` calculates independent Buy/Sell scores.
- Indicator definitions: RSI14, Bollinger20/2, MACD12/26/9, SMA50 and SMA200.
  Unavailable warmups and missing/expired fundamental components are neutral.
- Scan only completed exchange sessions, including the last session on holidays
  and weekends. Bitcoin sessions close at UTC midnight.
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

Daily caches use a date index and flat adjusted OHLCV columns. The downloader
normalizes Yahoo MultiIndex data, filters incomplete/non-session rows, merges
without dropping existing valid rows and atomically saves changed content only.
It reconciles 550 calendar days once per completed session and fetches a 14-day
overlap on reruns. `data/price_cache_state.json` binds reconciliation to cache
checksums. Reject mixed adjustment bases when provider history is incomplete.
Use temporary directories and mocked downloads for tests; review data diffs
separately from code changes.

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
