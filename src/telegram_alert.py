"""Telegram HTML transport; console output remains useful without credentials."""

import asyncio
import logging
import os

import telegram


def configured():
    return bool(
        os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")
    )


def send_alert(message):
    print(message)
    if not configured():
        return False
    asyncio.run(send(message))
    return True


async def send(message):
    # Telegram embeds its bot token in request paths; HTTP client INFO logs expose it.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    async with telegram.Bot(token=os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
        await bot.send_message(
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
