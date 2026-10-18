"""Telegram HTML transport; console output remains useful without credentials."""

import asyncio
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
    async with telegram.Bot(token=os.environ["TELEGRAM_BOT_TOKEN"]) as bot:
        await bot.send_message(
            chat_id=os.environ["TELEGRAM_CHAT_ID"],
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
