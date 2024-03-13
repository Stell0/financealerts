# FinanceAlerts

For each ticker in `config/tickers.txt` check RSI and bollinger bands and output a BUY/SELL signal. 

If a Telegram TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN environment variables are provided, alerts are also sent to the Telegram chat

## Telegram (optional):
```
TELEGRAM_CHAT_ID=-123456789
TELEGRAM_BOT_TOKEN=1234567890:XXX-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxX
```

## Launch:

```
python3 src/main.py
```

## How to setup your github action bot:

- fork this repository
- add into your https://github.com/YOUR_USERNAME/financealerts/settings/secrets/actions the following variables:
`DOCKERHUB_USERNAME`: your [dockerhub](https://hub.docker.com/) username
`DOCKERHUB_TOKEN`: dockerhub read/write access token https://hub.docker.com/settings/security
`TELEGRAM_CHAT_ID`: the [ID of the telegram chat](https://stackoverflow.com/questions/32423837/telegram-bot-how-to-get-a-group-chat-id) you whant your message to be sent
`TELEGRAM_BOT_TOKEN`: a telegram bot [token](https://core.telegram.org/bots/features#botfather)
- change all "stell0" occurrence in .github/workflows/*.yml with your username