For each ticker in `config/tickers.txt` check RSI and bollinger bands and output a BUY/SELL signal. 

If a Telegram TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN environment variables are provided, alerts are also sent to the Telegram chat

Telegram (optional):
```
TELEGRAM_CHAT_ID=-123456789
TELEGRAM_BOT_TOKEN=1234567890:XXX-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxX
```

Launch:

```
python3 src/main.py
```



