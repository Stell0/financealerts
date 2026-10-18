# FinanceAlerts / PaperTrader integration

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
