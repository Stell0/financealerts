# Repository guidance

## Project and layout

FinanceAlerts is a Python command-line application that downloads Yahoo Finance
prices, calculates technical indicators, and reports Buy/Sell and Short Watch
signals. Telegram delivery is optional. There is no web service or packaged Python
application.
The public web dashboard is a static GitHub Pages site; there is no backend.

- `src/main.py`: CLI entry point, full-universe scan orchestration, and per-ticker
  failure isolation.
- `src/registry.py`: additive ticker persistence, alias resolution and identity joins.
- `config/securities.csv`: allowlisted public PaperTrader identity snapshot, refreshed
  by normal scans and committed with runtime data for offline website builds.
- `src/dashboard.py`, `src/site_config.py`: deterministic site datasets, pure
  historical RSI markers and shared deployment/chart-link URL configuration.
- `site/`: lightweight ECharts UI, pinned npm packages and Playwright tests;
  generated `site/public/` and `node_modules/` must stay untracked.
- `scripts/build_site.py`, `scripts/migrate_rsi.py`: local-only site generation
  and bounded RSI backfill; neither may download market data.
- `config/short_watchlist.csv`: required, version-controlled `ticker,mode,sector`
  contract; never regenerate it from PaperTrader or copy its entries into longs.
- `src/papertrader_data.py`: read-only identity/assessment snapshots at one revision.
- `src/yahoo_finance_api.py`: Yahoo Finance downloads and daily CSV cache handling;
  also contains hourly-price and earnings-date helpers.
- `src/indicators.py`: TA-Lib calculations that add columns to pandas DataFrames.
- `src/ratings.py` and `src/rating_config.py`: RSI candidate triggers and independent
  weighted ratings. `src/signals.py` retains legacy helpers outside the current scan.
- `src/notifications.py`: linked HTML, sorting, splitting and bar-based delivery state.
- `src/telegram_alert.py`: console output and asynchronous HTML transport; HTTP
  client request logging is suppressed to keep bot tokens out of logs.
- `data/*.csv`: tracked price caches, not disposable build output.
- `data/price_cache_state.json` and `data/alert_state.json`: persistent runtime state.
- `requirements.txt`: pinned direct runtime dependencies, including yfinance.
- `Dockerfile`: pinned Python 3.12 image, TA-Lib wheel installation and startup.
- `.github/workflows/`: image builds, PR image builds, and scheduled execution
  with cache commits.

Local environments (`.venv/`, `fin/`), bytecode, scratch scripts, and debug CSVs
may exist outside tracked source. Check `git status --short` before editing and
preserve unrelated local work. Ticker management lives in `src/registry.py`;
the local untracked `src/load_tickers.py` is empty.

## Setup and execution

Run from the repository root: cache paths are relative to the working directory,
and `data/` must exist. Modules use sibling imports from `src/`.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use an existing environment if appropriate. The pinned TA-Lib Python binding
uses a wheel with its native library included on supported platforms. The
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
  securities plus `config/short_watchlist.csv`. Extend `MonitoredTicker.universe`
  (`long`, `short`, `research_only`) through the existing identity joins.
  Only longs persist in `config/tickers.txt`; remove previously saved bearish
  identities during synchronization. Local `active`/`research_only` classifications
  take precedence across every source, including environment and positional
  overrides. Validate CSV columns, symbols, modes, sectors and duplicate identities;
  missing/malformed short configuration must fail before saving the long registry.
  PaperTrader's optional `research_role` is legacy `long` when absent; either
  `short_candidate` or `short_research_only` excludes ordinary Buy/Sell and long
  persistence. Only local `active` enables short alerts; otherwise PaperTrader
  short roles stay research-only. A positional ticker overrides the scan only.
  Identity and assessment
  ingestion lives in `registry.py` and `papertrader_data.py`; never use PaperTrader
  prices or indicators. Preserve the GOOG/GOOGL and BTCUSD alias rules.
- RSI <= RSI_lower (30) triggers Buy and RSI >= RSI_upper (70) triggers Sell
  regardless of other factors. The additional open bands (30, 35) for Buy and
  (65, 70) for Sell require >= 7/10 directional non-RSI support. Exactly 35/65
  do not qualify. Bands extend five points inward from the configured thresholds.
  Reuse the existing directional technical/fundamental subscores, exclude RSI,
  and divide their weighted sum by the combined 75% weight. Compare unrounded
  support against the inclusive cutoff; bearish technicals and unfavorable
  fundamentals support Sell. Keep band/cutoff defaults in `rating_config.py`.
  `INDICATORS` no longer selects independent triggers. Ratings use defaults in
  `rating_config.py`: 25% RSI, 25% other technicals and 50% fundamentals.
  `ratings.py` calculates independent Buy/Sell scores; stars describe support
  for the direction independently of the notification eligibility check.
- Active shorts emit only `Short` at RSI(14) >= `SHORT_RSI_UPPER` (default 70,
  valid range 0–100). No Buy/Sell or near-threshold support bands apply. Reuse
  the ordinary Sell rating without changing its weights or RSI scoring scale.
  Research-only entries skip price scans entirely. Short rows show actual RSI
  and research status (current, partial, pending, stale, unsupported). Missing
  components stay neutral and stale fundamentals keep the existing expiry
  penalty. Research availability never implies a confirmed bearish thesis or
  an attractively priced put. Do not add options chains or trading execution.
- Indicator definitions: RSI14, Bollinger20/2, MACD12/26/9, SMA50 and SMA200.
  Unavailable warmups and missing/invalid fundamental components are neutral.
  Expired assessments give every directional fundamental factor 0/10 for both
  Buy and Sell, including risk. Do not mirror this penalty into a Sell reward.
  With the current weights, expired assessments cap either rating at 5/10
  (three stars) and cannot qualify the additional RSI bands. Extreme-RSI alerts
  remain eligible. Keep the configured weights and triggers unless requested.
- Scan only completed exchange sessions, including the last session on holidays
  and weekends. Bitcoin sessions close at UTC midnight.
- Telegram transport reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` at send time.
  Reports use HTML links and split only at complete ticker lines. Console-only
  runs print messages without advancing delivery state. `notifications.py` stores
  only successful sends in `data/alert_state.json`, keyed by symbol/direction and
  completed-bar date plus normalized OHLCV. No cooldown or transition gate exists.
  Short Watch follows Buy/Sell under `Short Watch — Put Candidates`, sorted by
  descending Sell-derived rating then ticker. `Short` delivery keys are separate
  from `Sell`; preserve UTF-16 length checks and complete-line HTML splitting.
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
Nonpositive adjusted prices trigger one full-history yfinance repair retry;
repaired data must pass the same cache integrity checks. SciPy supports repair.
Use temporary directories and mocked downloads for tests; review data diffs
separately from code changes.

Canonical caches are `Date,Open,High,Low,Close,Volume,RSI`. RSI is derived via the
existing `indicators.rsi` TA-Lib RSI(14), with empty warm-ups and 17 significant
digits. Quantize/serialize authoritative OHLCV first, then compute RSI from those
exact stored closes. Read with round-trip float precision. Keep derived columns
out of Yahoo normalization, adjustment comparisons and alert bar fingerprints.
Recompute the whole RSI series after corrected adjusted history. Migration must
preserve all valid rows and OHLCV text, support old column order, update matching
file hashes without advancing reconciliation dates, preserve corrupt caches,
ignore non-price CSVs and avoid unchanged writes. Main runs it automatically.

Build with `npm ci --prefix site` then `python scripts/build_site.py --output
site/public`; preview with `npm run preview --prefix site` at
`http://127.0.0.1:4173/financealerts/`. Builds use the committed public registry
and caches only, never live providers or secrets. Include every monitored
identity in the manifest even with missing/stale data. Preserve provider and
GOOG/GOOGL/BTC alias semantics; lazily load one history per selected security.
`SITE_BASE_URL` defaults to `https://stell0.github.io/financealerts/`; share its
validated HTTP(S) root between Telegram Chart links and site metadata. Relative
assets must work under the project subpath and custom domains.

Historical chart markers use pure configured RSI thresholds (Buy <= RSI_lower,
Sell >= RSI_upper), never fundamentals or support bands. First-entry mode only
suppresses consecutive markers in the same region. Label circles as retrospective
RSI conditions, not executed trades or evidence of Telegram deliveries; a short
security's red circle does not establish put value. Three aligned price/volume/RSI
grids share zoom/crosshairs; volume starts at zero, RSI is 0–100. Keep responsive
cleanup, reduced motion, accessible controls/table, visible error states and CSV
download. Chart code is adapted from PaperTrader's exact reference:
https://github.com/Kabutojira/PaperTrader/blob/pre-research-only-20261018/site/papertrader/scripts/research-charts.inline.ts
Also retain its responsive style and local ECharts packaging patterns, without
Quartz or unrelated indicators. ECharts is pinned locally with LICENSE/NOTICE.

Pages publication (`.github/workflows/pages.yml`) is serialized and main-only.
It checks out the current main tip on pushes, manual dispatch and completion of
the daily workflow, including failed scans that persisted partial progress.
`workflow_run` is required because GITHUB_TOKEN runtime pushes do not trigger
push workflows. Never publish pre-scan checkout data or expose runtime credentials.
Use official Pages artifact/deployment Actions and the `github-pages` environment.
Repository Settings → Pages → Source must be GitHub Actions.

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

CI builds the pinned Python 3.12 image and runs the offline suite without
credentials. The serialized daily workflow runs at 15:00 America/New_York (ET), one
hour before the regular 16:00 ET US market close. It builds the checkout and
commits only changed config/tickers.txt, config/securities.csv, data/*.csv and the two
runtime JSON state files. `scripts/commit_runtime.sh` skips empty commits and
refuses unrelated staged files. A scan failure still saves successful partial
progress, then fails the job. Jobs check out the current branch tip on reruns.
`scripts/push_runtime.sh` rebases and retries pushes without force; conflicts
preserve runtime files in a recovery artifact instead of overwriting upstream.
Manual dispatch defaults to a console-only dry run
without commits. Only the main image-build workflow publishes to Docker Hub.
For documentation changes, checking content, paths and the diff is sufficient.
Report what was actually checked and any checks that could not run.

For dashboard changes, build the site and run `npm test --prefix site` after
`npx --prefix site playwright install chromium` if no browser exists. Tests must
verify real chart rendering, SVG marker paths, synchronized zoom, navigation,
direct query links, Unicode-safe Telegram splitting and a mobile viewport; HTML
substring assertions alone do not establish chart correctness. The PR workflow
runs both Python and Playwright suites without publishing. Inspect screenshots
of representative desktop/mobile charts as part of visual QA.
