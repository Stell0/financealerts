import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from yahoo_finance_api import (
    latest_completed_session,
    normalize_prices,
    retrieve_daily_prices,
)

NOW = datetime(2026, 10, 18, 21, tzinfo=timezone.utc)


def bars(dates, closes=None):
    closes = closes or [100.0 + index for index in range(len(dates))]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [x + 2 for x in closes],
            "Low": [x - 2 for x in closes],
            "Close": closes,
            "Volume": 1000.0,
        },
        index=pd.to_datetime(dates),
    )


class PriceTests(unittest.TestCase):
    def test_completed_session_weekend_holiday_intraday_early_close_and_crypto(self):
        cases = [
            ((2026, 10, 18, 21), "TSLA", date(2026, 10, 16)),
            ((2026, 10, 19, 15), "TSLA", date(2026, 10, 16)),
            ((2026, 10, 19, 21), "TSLA", date(2026, 10, 19)),
            ((2026, 7, 3, 21), "TSLA", date(2026, 7, 2)),
            ((2026, 11, 27, 19), "TSLA", date(2026, 11, 27)),
            ((2026, 10, 18, 21), "BTC-USD", date(2026, 10, 17)),
        ]
        for instant, ticker, expected in cases:
            self.assertEqual(
                latest_completed_session(
                    ticker, datetime(*instant, tzinfo=timezone.utc)
                ),
                expected,
            )

    @patch("yahoo_finance_api.yf.download")
    def test_stable_reruns_preserve_latest_cached_row_and_retry_corrections(
        self, download
    ):
        with tempfile.TemporaryDirectory() as directory:
            download.return_value = bars(["2026-10-15", "2026-10-16"])
            first = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            path = Path(directory) / "TSLA.csv"
            before = path.read_bytes(), path.stat().st_mtime_ns
            download.return_value = bars(["2026-10-15"], [100.0])
            second = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            pd.testing.assert_frame_equal(first, second)
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))
            self.assertEqual(download.call_args.kwargs["start"], date(2026, 10, 2))
            download.return_value = bars(["2026-10-16"], [103.0])
            corrected = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            self.assertEqual(corrected.iloc[-1]["Close"], 103.0)
            self.assertEqual(len(corrected), 2)

    @patch("yahoo_finance_api.yf.download")
    def test_new_session_reconciles_adjusted_history_and_preserves_missing_sessions(
        self, download
    ):
        with tempfile.TemporaryDirectory() as directory:
            download.return_value = bars(["2026-10-14", "2026-10-15", "2026-10-16"])
            retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            download.return_value = bars(
                ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"],
                [50.0, 50.5, 51.0, 52.0],
            )
            result = retrieve_daily_prices(
                "TSLA",
                now=datetime(2026, 10, 19, 21, tzinfo=timezone.utc),
                cache_dir=directory,
            )
            self.assertEqual(result.loc["2026-10-14", "Close"], 50.0)
            self.assertEqual(result.loc["2026-10-15", "Close"], 50.5)
            self.assertEqual(result.iloc[-1]["Close"], 52.0)
            self.assertLess(download.call_args.kwargs["start"], date(2026, 1, 1))

    @patch("yahoo_finance_api.yf.download")
    def test_failed_download_preserves_cache_without_using_stale_session(
        self, download
    ):
        with tempfile.TemporaryDirectory() as directory:
            download.return_value = bars(["2026-10-16"])
            original = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            download.side_effect = RuntimeError("unavailable")
            pd.testing.assert_frame_equal(
                original, retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            )
            before = (Path(directory) / "TSLA.csv").read_bytes()
            with self.assertRaises(ValueError):
                retrieve_daily_prices(
                    "TSLA",
                    now=datetime(2026, 10, 19, 21, tzinfo=timezone.utc),
                    cache_dir=directory,
                )
            self.assertEqual(before, (Path(directory) / "TSLA.csv").read_bytes())

    @patch("yahoo_finance_api.yf.download")
    def test_invalid_old_header_and_empty_provider_are_isolated(self, download):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "TSLA.csv").write_text("Price,Close\nTicker,TSLA\nDate,\n")
            download.return_value = bars(["2026-10-16"])
            self.assertEqual(
                len(retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)), 1
            )
            download.return_value = pd.DataFrame()
            with self.assertRaises(ValueError):
                retrieve_daily_prices("BAD", now=NOW, cache_dir=directory)

    def test_multilevel_normalization_filters_incomplete_and_nontrading_rows(self):
        raw = bars(["2026-10-15", "2026-10-16", "2026-10-17", "2026-10-19"])
        raw.columns = pd.MultiIndex.from_product([raw.columns, ["TSLA"]])
        normalized = normalize_prices(raw, "TSLA", date(2026, 10, 16))
        self.assertEqual(
            list(normalized.index.date), [date(2026, 10, 15), date(2026, 10, 16)]
        )

    @patch("yahoo_finance_api.yf.download")
    def test_missing_sessions_preserved_when_adjustment_basis_is_unchanged(
        self, download
    ):
        with tempfile.TemporaryDirectory() as directory:
            download.return_value = bars(["2026-10-14", "2026-10-15", "2026-10-16"])
            retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            download.return_value = bars(["2026-10-16", "2026-10-19"], [102.0, 103.0])
            result = retrieve_daily_prices(
                "TSLA",
                now=datetime(2026, 10, 19, 21, tzinfo=timezone.utc),
                cache_dir=directory,
            )
            self.assertEqual(len(result), 4)
            self.assertEqual(result.loc["2026-10-15", "Close"], 101.0)
            # Reject a mixture of old adjusted prices and an incomplete new basis.
            Path(directory, "price_cache_state.json").unlink()
            download.return_value = bars(["2026-10-16", "2026-10-19"], [51.0, 51.5])
            before = Path(directory, "TSLA.csv").read_bytes()
            with self.assertRaisesRegex(ValueError, "incomplete adjusted-history"):
                retrieve_daily_prices(
                    "TSLA",
                    now=datetime(2026, 10, 19, 21, tzinfo=timezone.utc),
                    cache_dir=directory,
                )
            self.assertEqual(before, Path(directory, "TSLA.csv").read_bytes())

    @patch("yahoo_finance_api.yf.download")
    def test_larger_history_request_reconciles_short_cache_in_same_session(
        self, download
    ):
        with tempfile.TemporaryDirectory() as directory:
            download.return_value = bars(["2026-10-16"])
            retrieve_daily_prices("TSLA", period=20, now=NOW, cache_dir=directory)
            download.return_value = bars(["2026-01-05", "2026-10-16"], [50.0, 100.0])
            result = retrieve_daily_prices(
                "TSLA", period=550, now=NOW, cache_dir=directory
            )
            self.assertLess(download.call_args.kwargs["start"], date(2026, 1, 1))
            self.assertEqual(len(result), 2)
