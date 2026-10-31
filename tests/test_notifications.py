import json
import os
import tempfile
import unittest
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd

import telegram_alert
from notifications import (
    bar_identity,
    deliver,
    message_chunks,
    research_url,
    tradingview_url,
)
from registry import MonitoredTicker, read_securities, resolve


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs)["href"])


def candidate(
    ticker="TSLA", direction="Buy", score=9.0, day=date(2026, 10, 16), **changes
):
    security = {
        "security_id": "security_" + ticker,
        "ticker": ticker,
        "provider_symbol": ticker,
        "company_name": 'Example <A&B> "Inc."',
        "venue_mic": "XNAS",
        "research_page": f"data/wiki/securities/security_{ticker}.md",
    }
    row = {
        "item": MonitoredTicker(ticker, ticker, security),
        "direction": direction,
        "score": score,
        "date": day,
        "bar": pd.Series(
            {
                "Open": 100.0,
                "High": 102.0,
                "Low": 98.0,
                "Close": 101.0,
                "Volume": 1000.0,
            }
        ),
    }
    row.update(changes)
    return row


class NotificationTests(unittest.TestCase):
    def test_required_format_sections_sorting_and_html_escaping(self):
        rows = [
            candidate("LOW", score=3),
            candidate("HIGH", score=9),
            candidate("SELL", direction="Sell", score=7),
        ]
        message, included = list(message_chunks(rows))[0]
        self.assertLess(message.index(">HIGH<"), message.index(">LOW<"))
        self.assertLess(message.index("Buy:"), message.index("Sell:"))
        self.assertIn("| ⭐⭐⭐⭐⭐ |", message)
        self.assertNotIn("<A&B>", message)
        self.assertIn("Example &lt;A&amp;B&gt; &quot;Inc.&quot;", message)
        parser = Links()
        parser.feed(message)
        self.assertEqual(len(parser.links), 9)
        self.assertIn("symbol=NASDAQ%3AHIGH", parser.links[0])
        self.assertTrue(parser.links[1].endswith("/securities/security_HIGH"))
        self.assertEqual(len(included), 3)
        self.assertEqual(list(message_chunks([])), [])

    def test_real_ticker_and_research_links(self):
        rows = read_securities(
            Path("tests/fixtures/papertrader/securities.csv").read_text()
        )
        self.assertIn("symbol=NASDAQ%3AGOOG", tradingview_url(resolve("GOOG", rows)))
        self.assertIn("/securities/security_", research_url(resolve("GOOG", rows)))
        self.assertIn(
            "symbol=BITSTAMP%3ABTCUSD", tradingview_url(resolve("BTCUSD", rows))
        )
        self.assertIn(
            "symbol=EURONEXT%3APARRO", tradingview_url(resolve("PARRO.PA", rows))
        )
        self.assertIn("symbol=LSE%3AANIC", tradingview_url(resolve("ANIC.L", rows)))
        self.assertIn("symbol=KRX%3A108490", tradingview_url(resolve("108490", rows)))
        item = candidate()["item"]
        item.security["research_page"] = ""
        self.assertTrue(
            research_url(item).endswith("/security-catalog#security-security_TSLA")
        )
        item.security["research_page"] = 'https://evil.test/" onclick="bad'
        self.assertNotIn("evil", research_url(item))

    def test_unchanged_data_suppressed_new_session_and_correction_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "alert_state.json"
            sent = []
            sender = lambda message: sent.append(message) or True
            row = candidate()
            self.assertEqual(deliver([row], path, sender), 1)
            before = path.read_bytes(), path.stat().st_mtime_ns
            self.assertEqual(deliver([row], path, sender), 0)
            row["score"] = (
                5.0  # Score/fundamentals changes cannot defeat data-only suppression.
            )
            self.assertEqual(deliver([row], path, sender), 0)
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            row["date"] = date(2026, 10, 19)
            self.assertEqual(deliver([row], path, sender), 1)
            row["bar"]["Volume"] = 1001.0
            self.assertEqual(deliver([row], path, sender), 1)
            self.assertEqual(len(sent), 3)

    def test_failed_sends_and_console_mode_do_not_mark_delivered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"

            def fail(message):
                raise RuntimeError("send failed")

            with self.assertRaises(RuntimeError):
                deliver([candidate()], path, fail)
            self.assertFalse(path.exists())
            with (
                patch.dict(os.environ, {}, clear=True),
                patch("builtins.print") as output,
            ):
                self.assertEqual(deliver([candidate()], path), 0)
                output.assert_called_once()
            self.assertFalse(path.exists())
            self.assertEqual(deliver([candidate()], path, lambda message: True), 1)

    def test_line_safe_splitting_and_partial_delivery_retries(self):
        rows = [candidate(f"T{index:03}") for index in range(50)]
        chunks = list(message_chunks(rows))
        self.assertGreater(len(chunks), 1)
        for message, included in chunks:
            self.assertLessEqual(len(message.encode("utf-16-le")) // 2, 4096)
            parser = Links()
            parser.feed(message)
            self.assertEqual(len(parser.links), 3 * len(included))
            self.assertTrue(message.endswith("</a>"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            calls = []

            def sender(message):
                calls.append(message)
                if len(calls) > 1:
                    raise RuntimeError("second chunk failed")
                return True

            with self.assertRaises(RuntimeError):
                deliver(rows, path, sender)
            self.assertEqual(
                len(json.loads(path.read_text())["delivered"]), len(chunks[0][1])
            )
            remaining = []
            self.assertEqual(
                deliver(rows, path, lambda message: remaining.append(message) or True),
                len(rows) - len(chunks[0][1]),
            )
            self.assertNotIn(">T000<", "".join(remaining))

    def test_state_does_not_confuse_share_class_prices_or_direction(self):
        row = candidate()
        other = candidate("GOOGL")
        self.assertEqual(bar_identity(row), bar_identity(other))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.assertEqual(deliver([row, other], path, lambda message: True), 2)
            row["direction"] = "Sell"
            self.assertEqual(deliver([row], path, lambda message: True), 1)
            path.write_text("{bad json")
            with self.assertRaises(ValueError):
                deliver([row], path, lambda message: True)

    @patch("telegram_alert.telegram.Bot")
    def test_actual_transport_uses_html_and_propagates_send_errors(self, bot):
        client = AsyncMock()
        bot.return_value.__aenter__.return_value = client
        with (
            patch.dict(
                os.environ,
                {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"},
            ),
            patch("builtins.print"),
        ):
            self.assertTrue(telegram_alert.send_alert("<b>Buy:</b>"))
            self.assertEqual(client.send_message.call_args.kwargs["parse_mode"], "HTML")
            client.send_message.side_effect = RuntimeError("retry")
            with self.assertRaises(RuntimeError):
                telegram_alert.send_alert("message")

    def test_http_request_logs_do_not_expose_bot_token(self):
        import io
        import logging

        import httpx
        import telegram
        from telegram.request import HTTPXRequest

        token = "12345:private-token-for-offline-test"
        requests = []

        def response(request):
            requests.append(request)
            result = (
                {
                    "id": 12345,
                    "is_bot": True,
                    "first_name": "Test",
                    "username": "test_bot",
                }
                if request.url.path.endswith("/getMe")
                else {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": 123, "type": "private"},
                    "text": "sample",
                }
            )
            return httpx.Response(200, json={"ok": True, "result": result})

        transport = httpx.MockTransport(response)
        bot = telegram.Bot(
            token=token,
            request=HTTPXRequest(httpx_kwargs={"transport": transport}),
            get_updates_request=HTTPXRequest(httpx_kwargs={"transport": transport}),
        )
        stream = io.StringIO()
        root = logging.getLogger()
        handler = logging.StreamHandler(stream)
        old_level = root.level
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        try:
            with (
                patch.dict(
                    os.environ, {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": "123"}
                ),
                patch("telegram_alert.telegram.Bot", return_value=bot),
                patch("builtins.print"),
            ):
                self.assertTrue(telegram_alert.send_alert("sample"))
        finally:
            root.removeHandler(handler)
            root.setLevel(old_level)
        self.assertEqual(len(requests), 2)
        self.assertNotIn(token, stream.getvalue())
