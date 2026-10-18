import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from main import scan
from notifications import deliver
from papertrader_data import load_snapshot
from ratings import read_assessments
from registry import synchronize
from yahoo_finance_api import _calendar, calendar_name, latest_completed_session

FIXTURES = Path(__file__).parent / "fixtures/papertrader"


class IntegrationTests(unittest.TestCase):
    @patch("yahoo_finance_api.yf.download")
    def test_snapshot_universe_daily_scan_delivery_and_next_session(self, download):
        now = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tables = root / "PaperTrader/data/tables"
            tables.mkdir(parents=True)
            for name in ("securities.csv", "security_assessments.csv"):
                (tables / name).write_bytes((FIXTURES / name).read_bytes())
            forbidden = root / "PaperTrader/data/market"
            forbidden.mkdir()
            for name in ("latest.csv", "indicators.csv"):
                (forbidden / name).write_text("POISON: never a market input")
            securities, text = load_snapshot(directory=root / "PaperTrader")
            assessments = read_assessments(text)
            original = {
                p: p.read_bytes()
                for p in (root / "PaperTrader").rglob("*")
                if p.is_file()
            }
            ticker_file = root / "config/tickers.txt"
            ticker_file.parent.mkdir()
            ticker_file.write_text("GOOG\nBTCUSD\n")
            universe = synchronize(ticker_file, " TSLA GOOGL ", securities)
            self.assertEqual(len(universe), 93)
            self.assertEqual(
                sum(item.yahoo_symbol in {"GOOG", "GOOGL"} for item in universe), 1
            )
            by_symbol = {item.yahoo_symbol: item for item in universe}

            def provider(symbol, **kwargs):
                item = by_symbol[symbol]
                venue = (item.security or {}).get("venue_mic")
                completed = latest_completed_session(symbol, now, venue)
                calendar = _calendar(calendar_name(symbol, venue))
                dates = calendar.sessions_in_range(
                    completed - timedelta(days=550), completed
                )
                # Values depend only on date, not request length or cache history.
                ordinal = np.array(
                    [value.date().toordinal() for value in dates], dtype=float
                )
                if symbol in {"GOOG", "BTC-USD"}:
                    close = 1000.0 - (ordinal - 739000.0)
                elif symbol == "NVDA":
                    close = 100.0 + (ordinal - 739000.0)
                else:
                    close = 100.0 + (ordinal % 2)
                frame = pd.DataFrame(
                    {
                        "Open": close,
                        "High": close + 2,
                        "Low": close - 2,
                        "Close": close,
                        "Volume": 1000.0,
                    },
                    index=dates,
                )
                return frame.loc[
                    (frame.index.date >= kwargs["start"])
                    & (frame.index.date < kwargs["end"])
                ]

            download.side_effect = provider
            candidates, failures = scan(universe, assessments, now, root / "data")
            self.assertEqual(failures, [])
            self.assertEqual(
                {(row["item"].ticker, row["direction"]) for row in candidates},
                {("GOOG", "Buy"), ("BTCUSD", "Buy"), ("NVDA", "Sell")},
            )
            self.assertEqual(download.call_count, 93)
            messages = []
            state = root / "data/alert_state.json"
            self.assertEqual(
                deliver(
                    candidates, state, lambda message: messages.append(message) or True
                ),
                3,
            )
            self.assertIn("NASDAQ%3AGOOG", messages[0])
            self.assertIn("BITSTAMP%3ABTCUSD", messages[0])
            before = {p: p.read_bytes() for p in (root / "data").glob("*")}
            again, failures = scan(universe, assessments, now, root / "data")
            self.assertEqual(failures, [])
            self.assertEqual(
                deliver(again, state, lambda message: messages.append(message) or True),
                0,
            )
            self.assertEqual(
                before, {p: p.read_bytes() for p in (root / "data").glob("*")}
            )
            self.assertEqual(len(messages), 1)
            now = datetime(2026, 10, 19, 23, tzinfo=timezone.utc)
            next_candidates, failures = scan(universe, assessments, now, root / "data")
            self.assertEqual(failures, [])
            self.assertEqual(
                deliver(
                    next_candidates,
                    state,
                    lambda message: messages.append(message) or True,
                ),
                3,
            )
            self.assertEqual(len(messages), 2)
            self.assertEqual(original, {p: p.read_bytes() for p in original})
            self.assertNotIn("GOOGL", ticker_file.read_text().split())
