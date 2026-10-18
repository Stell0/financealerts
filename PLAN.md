# FinanceAlerts / PaperTrader integration

Current policy update (2026-10-18): expired assessments contribute 0/10 to every
fundamental factor for both Buy and Sell. This supersedes the original neutral
expiry fallback described in the milestone history below.
The latest user-approved rating weights are 25% RSI, 25% other technicals and
50% fundamentals, superseding the original 50% RSI weighting. Inclusive 30/70
RSI thresholds remain unconditional; the open (30, 35) Buy and (65, 70) Sell
bands additionally qualify with >= 7/10 normalized directional non-RSI support.

Implement the user-approved four milestones sequentially. Each repository owns
its own data; PaperTrader supplies identity and assessments only. No trading,
research refresh, portfolio filtering, cooldown, or historical backtesting.

- M1: Additive ticker registry, immutable identity joins, alias resolution,
  validated PaperTrader imports and watch-only Bitcoin.
- M2: Independent adjusted yfinance caches, completed sessions, standard TA-Lib
  indicators, RSI-only triggers and independent weighted 0–10 ratings.
- M3: Linked HTML Telegram output, sorted stars, line-safe splitting and
  successful-delivery state keyed only by completed-bar date and OHLCV.
- M4: Serialized daily pulls and commits, 23:15 Europe/Rome scheduling, full
  integration fixtures and updated usage documentation.

## Milestone evidence

### M1 — 2026-10-18

Initialized 93 monitored identities from PaperTrader's 92 registered securities,
explicit user tickers and deployed GitHub TICKER_LIST. GOOG uses GOOGL's immutable
identity but retains GOOG prices; BTCUSD uses BTC-USD. Registry writes are stable
and additive. PaperTrader imports missing verified identities through watchlist
validation with a Bitcoin-only, non-tradable cryptocurrency exception.

Validation: FinanceAlerts 6 offline tests; PaperTrader 51 targeted tests, Ruff,
MyPy, schema, wiki lint and portfolio reconciliation passed. Broad PaperTrader
runs exceeded local temporary disk quota; final regression will run in bounded
batches. Existing PaperTrader disabled-chart integrity findings are outside this
integration's scope; no research or portfolio records are rewritten.

### M2 — 2026-10-18

Repaired completed-session normalization and adjusted-price caching, corrected
SMA50 to 50 sessions, and replaced legacy signal selection with inclusive RSI
triggers. Added independent weighted ratings and neutral assessment fallback.
Pinned the small runtime dependency set and use TA-Lib wheels in the Python 3.12
container rather than building the obsolete native library. Offline tests cover
calendars, cache preservation/corrections, thresholds, indicator definitions and
fundamental validity; no tracked market cache is changed during validation.

### M3 — 2026-10-18

Added linked, sorted Telegram HTML reports, canonical research/catalog links,
exchange-qualified TradingView symbols and complete-line splitting. Delivery
state fingerprints only completed-bar date/OHLCV and advances per successful
chunk; console-only and failed sends do not mark delivery. Offline tests include
new-session/corrected-bar repeats, unchanged data, direction/share-class keys,
partial failures, HTML escaping and actual mocked transport. Python 3.12 Docker
build succeeded with pinned dependencies. No real Telegram message was sent.

### M4 — 2026-10-18

Integrated serialized daily execution at 23:15 Europe/Rome with public
single-revision PaperTrader pulls, offline validation, explicit partial-failure
reporting and commits limited to FinanceAlerts-owned runtime paths. Fixed empty
commit detection with real-Git regression tests. PR/branch builds no longer
publish images or scan with production credentials. Added realistic CSV
end-to-end coverage across 93 identities: identical reruns have no file changes
or repeated messages; a new trading session can alert again. README now documents
configuration, monitoring identities, cache and delivery behavior and deployment.

Final M4 evidence: 32 FinanceAlerts tests pass on Python 3.12 locally and in the
rebuilt container. Actionlint and runtime shell syntax pass. Live committed
PaperTrader read returned 92 securities and 83 assessments; GOOG and BTC-USD
price smoke checks returned the expected completed sessions without delivery.
An actual HTTPX mock-transport regression reproduces and prevents Telegram token
exposure in request logs. Full PaperTrader regression: 622 Python tests and four
Node tests pass, with schema/advice/wiki/portfolio/site checks passing. Strict
PaperTrader integrity still has 83 chart errors identical to its baseline; no
research data is rewritten to conceal them. Both branches need merging for daily
production synchronization. No live Telegram message or trade was made.

### Expired-assessment penalty — 2026-10-18

User correction: expired fundamentals must strongly lower both Buy and Sell
ratings. Each expired fundamental factor now receives 0/10 directional
favorability, including risk, for a zero contribution from the full 30% weight.
The penalty applies at expires_at, is never inverted into a Sell reward, and
leaves RSI triggers, weights, missing/invalid fallback and delivery state intact.
The last PLS.AX example drops from 7.0/four stars to 5.5/three stars. Added
regressions for both directions, exact expiry/timezones and this concrete alert;
all 36 offline tests pass locally and in the rebuilt Python 3.12 container.
Lint, formatting and whitespace checks pass. No live scan or Telegram delivery
was requested here.

### Alert eligibility and star weighting — 2026-10-18

User selected 25% RSI, 25% other technicals and 50% fundamentals. RSI remains
the sole inclusive 30/70 notification trigger. Stars give stronger influence
to fundamental support: valuation 20%, business quality 10%, thesis 7%, balance
sheet 5% and risk 8%; other technicals are Bollinger 10%, MACD 9% and trend 6%.
Expired research still contributes zero to both directions, now limiting either
rating to 5/10 (three stars). The previous PLS.AX bar now rates 3.7/two stars.
Missing/invalid research remains neutral; delivery state and repeat rules remain
unchanged. README recaps eligibility, directional support, expiry and stars.

Validation: all 37 offline tests pass locally and in the rebuilt Python 3.12
container. Added regressions show fundamentals change stars without changing
RSI eligibility, for both Buy and Sell. Lint, formatting and whitespace checks
pass. No price cache, delivery state or PaperTrader data changed; no Telegram
message was sent.

### Support-qualified RSI bands — 2026-10-18

Inclusive RSI <= 30 Buy and RSI >= 70 Sell candidates remain unconditional.
The open (30, 35) Buy and (65, 70) Sell bands now qualify when the corresponding
non-RSI support reaches 7/10. Reuse the same directional technical/fundamental
subscores, exclude RSI and normalize the remaining 75% weight before comparing
the unrounded support. No rating weights, expiry/missing-data policy or delivery
state rules change. README and AGENTS document the exact boundaries and formula.

Validation: 42 offline tests pass locally and in the rebuilt Python 3.12 image,
including strict 35/65 limits, unconditional inclusive 30/70 limits, exactly 7
versus just-below-7 support, weighted normalization, bearish Sell support and
existing market-data delivery suppression. Lint, formatting and diff checks
pass. No live Telegram delivery or market download was used for validation.
