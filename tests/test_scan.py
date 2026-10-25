import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from main import scan
from registry import MonitoredTicker


def prices(rising):
    close = np.arange(260, dtype=float) + 100
    if not rising:
        close = close[::-1].copy()
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": 1000.0,
        },
        index=pd.bdate_range(end="2026-10-16", periods=260),
    )


class ScanTests(unittest.TestCase):
    @patch("main.yahoo_finance_api.retrieve_daily_prices")
    def test_acquired_security_remains_registered_without_requesting_new_bars(self, retrieve):
        item = MonitoredTicker(
            "ATKR", "ATKR", {"security_id": "atkr", "status": "acquired"}
        )
        self.assertEqual(scan([item], {}), ([], []))
        retrieve.assert_not_called()

    @patch("main.yahoo_finance_api.retrieve_daily_prices")
    def test_full_universe_both_directions_and_per_ticker_failure_isolation(
        self, retrieve
    ):
        universe = [
            MonitoredTicker(
                name,
                name,
                {
                    "security_id": "sid_" + name,
                    "venue_mic": "XNAS",
                    "company_name": name,
                },
            )
            for name in ("BUY", "SELL", "SHORT", "ERROR")
        ]
        retrieve.side_effect = [
            prices(False),
            prices(True),
            prices(True).iloc[:5],
            ValueError("provider failed"),
        ]
        candidates, failures = scan(
            universe, {}, datetime(2026, 10, 18, tzinfo=timezone.utc)
        )
        self.assertEqual(
            [(row["item"].ticker, row["direction"]) for row in candidates],
            [("BUY", "Buy"), ("SELL", "Sell")],
        )
        self.assertEqual(failures, ["SHORT", "ERROR"])
        self.assertEqual(retrieve.call_count, len(universe))
        self.assertEqual(retrieve.call_args.kwargs["period"], 550)
