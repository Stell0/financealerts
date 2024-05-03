# FinanceAlerts

For each ticker in environment var TICKER_LIST, the software checks RSI and bollinger bands and output a BUY/SELL signal. 

If a Telegram TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN environment variables are provided, alerts are also sent to the Telegram chat

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

**_NOTE:_** you can add ticker from London stock exchange adding a .L to the ticker, and .AX for Australian stock exchange e.g. ANIC.L, PLS.AX

then wait ⏱️  (cron is launched once a day)
