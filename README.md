# FinanceAlerts

For each ticker in environment var TICKER_LIST, the software checks RSI and bollinger bands and output a BUY/SELL signal. 

If a Telegram TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN environment variables are provided, alerts are also sent to the Telegram chat. 

INDICATORS env is the list of indicators that can be used. Possible values: RSI, BB, SMA, MACD

## Telegram (optional):
```
TELEGRAM_CHAT_ID=-123456789
TELEGRAM_BOT_TOKEN=1234567890:XXX-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxX
```

## Launch:

```
export TICKER_LIST="TSLA INTC"
python3 src/main.py
```

or

```
python3 src/main.py INTC
```

## How to setup your github action bot:

- fork this repository

- add into your https://github.com/YOUR_USERNAME/financealerts/settings/secrets/actions the following variables:
`DOCKERHUB_USERNAME`: your [dockerhub](https://hub.docker.com/) username
`DOCKERHUB_TOKEN`: dockerhub read/write access token https://hub.docker.com/settings/security
`TELEGRAM_CHAT_ID`: the [ID of the telegram chat](https://stackoverflow.com/questions/32423837/telegram-bot-how-to-get-a-group-chat-id) you whant your message to be sent
`TELEGRAM_BOT_TOKEN`: a telegram bot [token](https://core.telegram.org/bots/features#botfather)
`TICKER_LIST`
- change all "stell0" occurrence in .github/workflows/*.yml with your username


> **_NOTE:_**  go to the Actions tab and enable the scheduled workflows because they are disabled for the forked repositories.

- add into your [action secrets](https://github.com/YOUR_USERNAME/financealerts/settings/secrets/actions)
 the following variables:

`TELEGRAM_CHAT_ID`: the [ID of the telegram chat](https://stackoverflow.com/questions/32423837/telegram-bot-how-to-get-a-group-chat-id) you whant your message to be sent

`TELEGRAM_BOT_TOKEN`: a telegram bot [token](https://core.telegram.org/bots/features#botfather)

- Then add in your [action variables](https://github.com/YOUR_USERNAME/financealerts/settings/variables/actions)the variable with the list of tickers to analyze

`TICKER_LIST`: list of tickers
```
TSLA
INTC
AAPL
```

**_NOTE:_** you can add ticker from London stock exchange adding a .L to the ticker, and .AX for Australian stock exchange e.g. ANIC.L, PLS.AX. 

then wait ⏱️  (cron is launched once a day)


## PaperTrader ticker registry

The monitored universe is the additive union of `config/tickers.txt`, whitespace-
separated `TICKER_LIST`, and PaperTrader's registered securities. A positional
symbol remains an explicit one-ticker scan override. The registry is sorted and
written only when its contents change. GOOG/GOOGL use one PaperTrader identity;
explicit GOOG retains its own Yahoo Finance prices. BTCUSD uses BTC-USD prices.

By default FinanceAlerts reads PaperTrader's public identity and assessment tables
at one resolved commit SHA. Set `PAPERTRADER_REVISION` to pin a full SHA, or
`PAPERTRADER_DIR` to read a local checkout (use committed data for production).
It never reads PaperTrader market caches or technical indicators. Missing symbols
converge when PaperTrader pulls the committed FinanceAlerts file through its
validated watchlist importer; each repository writes only its own data.

Offline registry checks: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.

## RSI ratings and independent prices

FinanceAlerts downloads its own adjusted daily OHLCV series from yfinance. It
never uses PaperTrader market prices, technical indicators, timing scores or
historical reference prices. Indicators are RSI(14), Bollinger(20,2),
MACD(12,26,9), SMA50 and SMA200. Signals from the older `INDICATORS` selector are
replaced by RSI-only triggers: Buy at RSI <= `RSI_lower` (30), Sell at RSI >=
`RSI_upper` (70). Both directions apply to every monitored security.

The independent Buy/Sell scores use defaults in `src/rating_config.py`: RSI 50%,
Bollinger 8%, MACD 7%, moving averages 5%, valuation 12%, business quality 6%,
thesis 4%, balance sheet 3%, risk penalty 5%. RSI scores start at 5 on the trigger
and increase by 0.5 per RSI point beyond it, capped at 10. Bollinger scores measure
position within the bands; MACD combines line/signal position and histogram
movement; moving averages combine 50/200 trend and price/50 position. Missing
technical warm-up values are neutral. There are no additional signal vetoes.

Fundamentals join on immutable security_id, scale from 0–100 to 0–10 and favor
quality/value for Buy and weakness/risk for Sell. Missing, expired or invalid
components become 5/10 without changing weights or refreshing research. Scores
are rounded to one decimal. Stars use (0–2], (2–4], (4–6], (6–8], (8–10], with
one star also at zero.

Exchange calendars select the most recent completed daily session, including
holidays, half days and daylight-saving changes. Bitcoin days close at UTC
midnight. Valid caches are merged without dropping their last row. The retained
550-day adjusted history is reconciled once per new completed session, including
corporate-action adjustments; reruns fetch a 14-day overlap for corrections.
Cache metadata binds the last full reconciliation to the CSV checksum. Mixed
adjustment revisions with missing historical rows fail per ticker and preserve
the cache for retry. A failed provider may use a cache only when it already
contains the latest completed session. Other tickers continue independently.
