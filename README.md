# FinanceAlerts

Daily RSI Buy/Sell notifications enriched with PaperTrader fundamental
assessments. FinanceAlerts independently downloads Yahoo Finance prices,
calculates TA-Lib indicators, rates both directions, and optionally sends one
compact Telegram report. It never trades or modifies PaperTrader's portfolio.

## Run locally

Use Python 3.12+ and the pinned runtime packages. TA-Lib wheels include the native
library on supported platforms.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# Scan the merged monitored universe, printing messages only.
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID .venv/bin/python src/main.py

# Explicit single-ticker scan override.
env -u TELEGRAM_BOT_TOKEN -u TELEGRAM_CHAT_ID .venv/bin/python src/main.py GOOG
```

Run from the repository root. `.env` is not loaded automatically. Both commands
retrieve live market data and may update local caches and the ticker registry.
Console-only execution never advances Telegram delivery state. A ticker/provider
failure is reported, other tickers continue, and the final exit status is nonzero.

```sh
docker build -t financealerts:local .
docker run --rm -v "$PWD/config:/app/config" -v "$PWD/data:/app/data" \
  -e TICKER_LIST="TSLA INTC" financealerts:local
```

Mount both directories to preserve ticker, price and delivery state between runs.
Pass Telegram credentials with `-e TELEGRAM_BOT_TOKEN -e TELEGRAM_CHAT_ID` when
actual delivery is wanted.

## Tickers and PaperTrader synchronization

`config/tickers.txt` contains one symbol per line. The scan merges this file,
whitespace-separated `TICKER_LIST`, and every registered PaperTrader security,
then saves the normalized, deduplicated list in stable order. Synchronization is
additive; no security is deleted automatically. The initial file includes all
92 PaperTrader securities plus the supplied user symbols and deployed environment
list, resulting in 93 monitored identities including Bitcoin.

GOOG and GOOGL share the existing Alphabet `security_id` and assessment. Explicit
GOOG wins in the monitored file and uses **GOOG prices**, never GOOGL prices.
BTCUSD/BTC-USD use one monitored identity with Yahoo symbol `BTC-USD`. Other
registry tickers use provider-qualified symbols such as `108490.KQ` and `AKE.PA`.

FinanceAlerts resolves PaperTrader's public `main` commit once and reads only
`data/tables/securities.csv` and `security_assessments.csv` at that SHA. Set
`PAPERTRADER_REVISION` to a full commit SHA, or `PAPERTRADER_DIR` to a local
checkout. Local reads are useful for testing; use committed snapshots in daily
production. A missing assessment table produces neutral fundamentals; a failed
identity snapshot read is an explicit error.

PaperTrader's existing daily preparation pulls the committed FinanceAlerts file
and imports genuinely missing securities through `papertrader watchlist import`
validation. Failed identities are reported as operational issues. Each repository
writes and commits only its own files, with no foreign write token. Changes can
converge over the next daily cycle. Merge both implementation branches before
expecting production synchronization.

Bitcoin is a watch-only `cryptocurrency`, with off-exchange MIC `XOFF`, unknown
country `ZZ` and a 24/7 monitoring calendar. PaperTrader's allowed trading
instruments and venues remain unchanged: cryptocurrency orders are prohibited.

## Indicators and ratings

Only RSI(14) triggers alerts: Buy at RSI <= `RSI_lower` (default 30), Sell at
RSI >= `RSI_upper` (default 70). Both directions apply to the entire universe.
The former `INDICATORS` selector no longer triggers independent signals.

The independent Buy/Sell ratings are weighted sums of 0–10 subscores. Defaults
live in `src/rating_config.py`: RSI 50%, Bollinger 8%, MACD 7%, SMA50/SMA200 5%,
valuation 12%, business quality 6%, thesis 4%, balance sheet 3%, risk penalty 5%.
RSI starts at 5 on its threshold and increases by 0.5 per point beyond it, capped
at 10. Bollinger(20,2) measures band position, MACD(12,26,9) combines line/signal
position and histogram movement, and moving averages combine 50/200 trend with
price/50 position. Unavailable technical warm-ups remain neutral; insufficient
RSI history is reported per ticker.

PaperTrader components join by immutable `security_id`, scale from 0–100 to 0–10,
and favor value/quality for Buy and weakness/risk for Sell. Expired assessments
receive 0/10 for every fundamental factor in both directions, including risk.
Their entire 30% fundamental contribution is zero, removing the 1.5-point neutral
contribution. Expiry starts exactly at `expires_at`; it never boosts Sell scores.
`EXPIRED_FUNDAMENTAL_SCORE` is defined alongside the weights in
`src/rating_config.py`. Missing or invalid assessments/components remain neutral
at 5/10. Weights and RSI triggers stay unchanged; expiry does not block a
qualifying alert or refresh research.
FinanceAlerts never reads PaperTrader prices, technical series, `timing_score`
or `reference_price`, and never refreshes research. Scores round to one decimal.
Stars use 0–2: one, over 2–4: two, over 4–6: three, over 6–8: four, over 8–10: five.

## Completed sessions and caches

Exchange calendars select the most recent completed daily session, including
holidays, half days and DST. Bitcoin days close at UTC midnight. Daily caches
contain normalized adjusted OHLCV; SMA50 uses 50 trading sessions.

Cache updates preserve valid rows and deduplicate by date. Once per new completed
session, the retained 550-calendar-day adjusted history is reconciled, including
historical corrections and corporate-action adjustments. Reruns fetch a 14-day
overlap to detect corrected recent bars. `data/price_cache_state.json` binds the
last full reconciliation to the CSV checksum. Incomplete historical revisions
that could mix adjustment bases fail per ticker and preserve the previous cache
for retry. Provider failures may use a valid cache only when it already contains
the latest completed session. No run requires the candle date to equal today.

## Telegram output and retries

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to enable HTML delivery. Buy comes
before Sell, each sorted by descending rating. Each complete ticker line contains
linked ticker, stars and linked company name. TradingView uses the analyzed
market symbol and exchange; Bitcoin uses `BITSTAMP:BTCUSD`. Company links use
existing PaperTrader research pages, otherwise the security's catalog anchor.
Symbols awaiting registry import link to the catalog until their entry exists.

Messages split at complete ticker lines within Telegram's limit. No message is
created without new qualifying candidates. `data/alert_state.json` stores only
successful deliveries, keyed by Yahoo symbol/direction and a fingerprint of the
latest completed bar's date and normalized OHLCV. A new session or corrected bar
can notify again; unchanged data cannot. Scores, research changes and elapsed
time do not independently cause repeats. No cooldown, transition gate or
portfolio filter exists.

State persists after each successful chunk. Failed chunks remain retryable;
console-only output never marks delivery. Corrupt state fails explicitly. If a
process is interrupted after Telegram accepts a message but before state is saved,
its delivery cannot be proven; retain the committed state and inspect the run
before manual replay.

## Daily automation

The serialized daily workflow runs at **23:15 Europe/Rome**, after US regular
close. It builds the checked-out source, runs offline tests, pulls a consistent
PaperTrader snapshot, merges tickers, scans, delivers and commits changed ticker,
price-cache and delivery-state files. No-change runs skip commits. Partial
successful deliveries and caches are committed even if another ticker/send fails;
the run still reports failure. GitHub schedules may start later than requested.

Manual dispatch defaults to `dry_run=true`: live provider reads and console
output, with no Telegram delivery or commits. Set it false for normal execution.
The PR/branch workflow builds and tests without credentials or publication. The
separate image workflow publishes `stell0/financealerts:latest` on main, using
`DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`; daily scans build their own image.
Configure `TICKER_LIST`, `RSI_LOWER` and `RSI_UPPER` as optional Actions variables,
and Telegram credentials as Actions secrets. Scheduled workflows must be enabled
on forks.

## Offline verification

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Tests use realistic PaperTrader CSV fixtures, synthetic prices and mocked network
and Telegram boundaries. They cover identity/alias convergence, score and session
boundaries, cache corrections, full-universe Buy/Sell scans, HTML links/splitting,
retry state and repeated/new-session end-to-end runs. Runtime commit tests create
isolated Git repositories and prove no-change runs avoid empty commits and
unrelated files remain unstaged. No test sends a real message or changes tracked
price caches.
