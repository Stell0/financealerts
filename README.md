# FinanceAlerts

Daily RSI Buy/Sell and Short Watch notifications enriched with PaperTrader fundamental
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

`config/tickers.txt` contains one long-universe symbol per line. The scan merges
this file, whitespace-separated `TICKER_LIST`, PaperTrader securities and
`config/short_watchlist.csv`, resolving canonical security identities before
classification and deduplication. Only long securities are saved to
`config/tickers.txt`, in stable order. Long synchronization is additive except
that entries classified as bearish are removed from that saved long file.
The initial long file includes all
92 PaperTrader securities plus the supplied user symbols and deployed environment
list, resulting in 93 monitored identities including Bitcoin.

GOOG and GOOGL share the existing Alphabet `security_id` and assessment. Explicit
GOOG wins in the monitored file and uses **GOOG prices**, never GOOGL prices.
BTCUSD/BTC-USD use one monitored identity with Yahoo symbol `BTC-USD`. Other
registry tickers use provider-qualified symbols such as `108490.KQ` and `AKE.PA`.

The translation table is PaperTrader's `securities.csv`: `ticker` resolves to
`provider_symbol`, joined by `security_id` in `src/registry.py`. Verified mappings
for the price failures in the October 24, 2026 run are:

| Saved or registry symbol | Yahoo Finance symbol |
| --- | --- |
| AD / AD.AS | AD.AS |
| AKE / AKE.PA | AKE.PA |
| ANIC.L | ANIC.L |
| ATKR | ATKR |
| BAS / BAS.DE | BAS.DE |
| BTCUSD / BTC-USD | BTC-USD |
| EVK / EVK.DE | EVK.DE |
| FUC.F | FUC.F |
| NIB.F | NIB.F |
| PARRO.PA | PARRO.PA |
| PRX / PRX.AS | PRX.AS |
| SSU.VI | SSU.VI |
| SSUN.VI | SSUN.VI |
| SU / SU.PA | SU.PA |
| YEC.F | YEC.F |

Yahoo recognized all these symbols during verification; that run's errors were
missing completed bars or incomplete adjusted-history reconciliation. A different
exchange, ADR or share class requires its own verified identity, currency and
calendar. In particular, Samsung's common and preferred GDRs remain separate.
Securities explicitly marked `acquired` by PaperTrader stay in the saved universe
and retain their caches, but the scan skips requests for post-acquisition candles.

FinanceAlerts resolves PaperTrader's public `main` commit once and reads only
`data/tables/securities.csv` and `security_assessments.csv` at that SHA. Set
`PAPERTRADER_REVISION` to a full commit SHA, or `PAPERTRADER_DIR` to a local
checkout. Local reads are useful for testing; use committed snapshots in daily
production. A missing assessment table produces neutral fundamentals; a failed
identity snapshot read is an explicit error.

Assessment imports accept both legacy `expires_at` and current `valid_until`
(legacy `expires_at` takes precedence if both columns exist). Missing component
columns are logged by name and remain neutral individually. Valid expired rows
still receive the expiry penalty even when component columns are absent. The
PaperTrader score contract supplies optional `valuation_score`,
`business_quality_score`, `thesis_score`, `balance_sheet_score` and `risk_penalty`.
FinanceAlerts uses these fields directly with the existing weights and directional
risk inversion. Rubric version, source details and valuation reference metadata
remain provenance rather than additional rating factors. Historical scores stay
empty until sourced research supplies them; headers alone do not create support.

PaperTrader's existing daily preparation pulls the committed FinanceAlerts file
and imports genuinely missing securities through `papertrader watchlist import`
validation. Failed identities are reported as operational issues. Each repository
writes and commits only its own files, with no foreign write token. Changes can
converge over the next daily cycle. Merge both implementation branches before
expecting production synchronization.

### Separate bearish research universe

`config/short_watchlist.csv` is version-controlled configuration with the exact
header `ticker,mode,sector`. Its `active` entries belong to the `short` universe;
`research_only` entries remain recorded but skip price scans and never alert,
including positional ticker overrides. Invalid symbols, modes, missing sectors,
malformed rows and duplicate identities fail explicitly. This file is required
and is never regenerated from PaperTrader.

The initial active list is **FCEL, AI, SPCE, CIFR, WULF, BBAI, APLD, ONDS, AEVA,
PDYN**. The initial research-only list is **KSCP, MVIS, PSNY, PLUG, ARQQ, SPIR**.
Research-only candidates may have limited options liquidity or other constraints.

PaperTrader's optional `research_role` accepts `long`, `short_candidate` and
`short_research_only`. An absent column preserves legacy long behavior.
Either short role excludes a security from ordinary Buy/Sell alerts and the
saved long file; neither enables Short Watch alerts by itself. Only a local
`active` entry enables those alerts. Local short classification overrides all
other sources, including `TICKER_LIST` and legacy PaperTrader entries. Resolution
uses the existing security identity, provider symbol, exchange and alias rules;
overlapping sources produce one monitored identity. Acquired-security handling
and GOOG/GOOGL price selection remain unchanged.

Active shorts alert only at **RSI(14) >= 70**, independently configurable with
`SHORT_RSI_UPPER` (0–100). They never generate Buy or conventional Sell alerts,
and do not use the long universe's 65–70 Sell support band. Stars reuse the
ordinary Sell directional score and weights, including its RSI scoring scale;
changing the short trigger does not change that scale. Current PaperTrader
fundamentals enrich the score. Missing or invalid components remain neutral;
stale assessments retain the existing zero fundamental contribution.

Short Watch means the technical condition is satisfied. It does not establish
that a put is attractively priced. FinanceAlerts does not fetch options chains,
assess options liquidity, execute trades or manage a portfolio.

Bitcoin is a watch-only `cryptocurrency`, with off-exchange MIC `XOFF`, unknown
country `ZZ` and a 24/7 monitoring calendar. PaperTrader's allowed trading
instruments and venues remain unchanged: cryptocurrency orders are prohibited.

## Indicators and ratings

RSI(14) determines the eligible direction for the ordinary long universe. With
default thresholds, notification eligibility is:

| Direction | RSI condition | Required non-RSI directional support |
| --- | --- | --- |
| Buy | RSI <= 30 | None |
| Buy | 30 < RSI < 35 | >= 7/10 Buy support |
| Sell | RSI >= 70 | None |
| Sell | 65 < RSI < 70 | >= 7/10 Sell support |

Otherwise there is no notification. Exactly 35 and 65 are excluded; exactly 30
and 70 qualify regardless of other factors. Non-RSI support reuses the same
directional Bollinger, MACD, moving-average and fundamental subscores as stars:
`support = sum(weight * subscore for non-RSI factors) / 0.75`.
RSI is excluded, and support is compared with the inclusive 7/10 cutoff before
rounding. Strong Sell support means bearish technicals and unfavorable
fundamentals. The open five-point bands sit above `RSI_lower` (default 30) and
below `RSI_upper` (default 70); defaults live in `src/rating_config.py`.

Buy flags an oversold candidate for review; Sell flags an overbought candidate.
These conditions identify price extremes, not a fundamental recommendation or
an instruction to trade. A high star rating alone does not create a notification.
The former `INDICATORS` selector no longer triggers independent signals.

Stars express weighted support for the selected direction. Ratings give 25% to
RSI, 25% to other technicals and 50% to fundamentals, so a more extreme RSI has
less influence than it had under the original 50% RSI weighting. The independent
Buy/Sell ratings sum 0–10 subscores using defaults in `src/rating_config.py`:

| Factor | Weight | Rationale |
| --- | ---: | --- |
| RSI(14) | 25% | Strength of the oversold/overbought extreme |
| Bollinger Bands | 10% | Position near the lower/upper band |
| MACD | 9% | Momentum reversal or deterioration |
| SMA50/SMA200 | 6% | Trend confirmation |
| PaperTrader valuation | 20% | Fundamental value or overvaluation |
| PaperTrader business quality | 10% | Business strength or weakness |
| PaperTrader thesis | 7% | Investment thesis strength or weakness |
| PaperTrader balance sheet | 5% | Financial strength or weakness |
| PaperTrader risk penalty | 8% | Lower risk favors Buy; higher risk favors Sell |

RSI starts at 5 on its threshold and increases by 0.5 per point beyond it, capped
at 10. Its maximum contribution is 2.5 rating points; going from RSI 30 to 20
adds 1.25 Buy points before rounding. Bollinger(20,2) measures band position,
MACD(12,26,9) combines line/signal position and histogram movement, and moving
averages combine 50/200 trend with price/50 position. Unavailable technical
warm-ups remain neutral; insufficient RSI history is reported per ticker.

PaperTrader components join by immutable `security_id`, scale from 0–100 to 0–10,
and favor value/quality for Buy and weakness/risk for Sell. Expired assessments
receive 0/10 for every fundamental factor in both directions, including risk.
Their entire 50% fundamental contribution is zero, removing the 2.5-point neutral
contribution. Consequently, expired research limits either rating to 5/10
(three stars), even with maximum technical support. Expiry starts exactly at
`expires_at`; it never boosts Sell scores.
`EXPIRED_FUNDAMENTAL_SCORE` is defined alongside the weights in
`src/rating_config.py`. Missing or invalid assessments/components remain neutral
at 5/10. Expiry does not change the weighting or unconditional RSI triggers,
or refresh research. With zero fundamental support, even maximum other technicals
give only 3.33/10 non-RSI support, so expired assessments cannot qualify the
additional Buy/Sell bands. Extreme-RSI alerts remain eligible.
FinanceAlerts never reads PaperTrader prices, technical series, `timing_score`
or `reference_price`, and never refreshes research. Scores round to one decimal.
Stars use 0–2: one, over 2–4: two, over 4–6: three, over 6–8: four, over 8–10: five.
More stars mean stronger support within this model, not a probability of profit.
Sell is calculated independently, not as 10 minus Buy. PaperTrader's categorical
Sell/Avoid label is not an alert veto; its component scores and validity affect
stars. For the previous PLS.AX alert's same market bar and expired assessment,
the current model gives 3.7/10 (two stars), versus the original 7.0/four stars.

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
for retry, reporting the number of missing valid sessions. Nonpositive adjusted
prices trigger one full-history retry with yfinance's price repair, supported by
the pinned SciPy dependency. Repaired history must pass the same normalization,
completed-session and adjustment-basis checks; incomplete changed histories still
fail without modifying the cache. Provider failures may use a valid cache only when
it already contains the latest completed session. No run requires the candle date
to equal today.

## Telegram output and retries

Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to enable HTML delivery. Buy comes
before Sell, each sorted by descending rating. Short Watch follows both under
**Short Watch — Put Candidates**, sorted by descending bearish-support rating,
then ticker. Each complete ticker line contains
linked ticker, stars and linked company name. TradingView uses the analyzed
market symbol and exchange; Bitcoin uses `BITSTAMP:BTCUSD`. Company links use
existing PaperTrader research pages, otherwise the security's catalog anchor.
Symbols awaiting registry import link to the catalog until their entry exists.
Short Watch rows also include actual RSI and `Research: current`, `partial`,
`pending`, `stale` or `unsupported`. Current means a valid assessment with every
scoring component available; partial means some components are unavailable;
pending means no usable assessment row; stale means its validity has expired;
unsupported means invalid validity metadata or no usable scoring components.
These statuses describe assessment availability, not confirmation of a bearish
thesis. Canonical PaperTrader links appear once the security is registered.

Messages split at complete ticker lines within Telegram's limit. No message is
created without new qualifying candidates. `data/alert_state.json` stores only
successful deliveries, keyed by Yahoo symbol/direction and a fingerprint of the
latest completed bar's date and normalized OHLCV. A new session or corrected bar
can notify again. `Short` and `Sell` use independent delivery keys. Unchanged data
cannot notify again. Scores, research changes and elapsed
time do not independently cause repeats. No cooldown, transition gate or
portfolio filter exists.

State persists after each successful chunk. Failed chunks remain retryable;
console-only output never marks delivery. Corrupt state fails explicitly. If a
process is interrupted after Telegram accepts a message but before state is saved,
its delivery cannot be proven; retain the committed state and inspect the run
before manual replay.

## Daily automation

The serialized daily workflow runs at **15:00 ET (America/New_York)**, one hour
before the regular 16:00 ET US market close, with daylight saving handled automatically.
It builds the checked-out source, runs offline tests, pulls a consistent
PaperTrader snapshot, merges tickers, scans, delivers and commits changed ticker,
price-cache and delivery-state files. No-change runs skip commits. Partial
successful deliveries and caches are committed even if another ticker/send fails;
the run still reports failure. GitHub schedules may start later than requested.

Daily jobs check out the current branch tip, including on reruns, so an earlier
attempt's committed delivery state is loaded. Runtime pushes fetch and rebase
onto upstream before pushing, retrying up to three times without force. Conflicts
fail explicitly and preserve local runtime changes in a seven-day
`runtime-state-<run>-<attempt>` artifact. Reconcile its delivery state with the
branch before replaying a failed send-capable run; do not overwrite newer state.
The final scan log summarizes processed, acquired, candidate and failed counts.
Unavailable fundamental scores are grouped in one warning per assessment,
identified by security ID; neutral values and expiry penalties are unchanged.

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
retry state and repeated/new-session end-to-end runs. Short-watchlist tests cover
both PaperTrader schemas, all 16 imports, classification precedence, independent
Short delivery keys and a console-only CLI integration with mocked Yahoo data
and Telegram credentials disabled. Runtime commit tests create
isolated Git repositories and prove no-change runs avoid empty commits and
unrelated files remain unstaged. No test sends a real message or changes tracked
price caches.
