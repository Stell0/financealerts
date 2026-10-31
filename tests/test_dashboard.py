import csv
import hashlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from dashboard import build_site, historical_signals
from indicators import rsi
from notifications import bar_identity, ticker_line
from registry import MonitoredTicker, read_securities, save_securities
from site_config import chart_url, site_base_url
from yahoo_finance_api import COLUMNS, enrich_price_csv, migrate_caches, normalize_prices, retrieve_daily_prices
from test_notifications import candidate, Links
from test_scan import prices as raw_prices

NOW = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)


def prices(rising):
    return normalize_prices(raw_prices(rising), "TSLA", NOW.date())


class RsiCacheTests(unittest.TestCase):
    def test_migration_preserves_prices_and_metadata_and_is_byte_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = prices(True).to_csv(float_format="%.12g", index_label="Date")
            path = root / "TSLA.csv"
            path.write_text(original)
            old_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata = {"TSLA": {"sha256": old_hash, "full_session": "2026-10-16", "start": "2025-04-14"}}
            state = root / "price_cache_state.json"
            state.write_text(json.dumps(metadata))
            alert = root / "alert_state.json"
            alert.write_text('{"version":1,"delivered":{}}\n')
            alert_before = alert.read_bytes()
            result = migrate_caches(root, now=NOW)
            self.assertEqual(result["migrated"], 1)
            self.assertEqual(result["errors"], {})
            old_rows = list(csv.reader(io.StringIO(original)))
            new_rows = list(csv.reader(io.StringIO(path.read_text())))
            self.assertEqual(new_rows[0], ["Date", *COLUMNS, "RSI"])
            self.assertEqual(old_rows, [row[:6] for row in new_rows])
            self.assertTrue(all(row[-1] == "" for row in new_rows[1:15]))
            frame = pd.read_csv(path, index_col=0, float_precision="round_trip")
            expected = rsi(frame[COLUMNS].astype(float))["RSI"]
            np.testing.assert_array_equal(frame["RSI"], expected)
            updated = json.loads(state.read_text())
            self.assertEqual(updated["TSLA"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(updated["TSLA"]["full_session"], "2026-10-16")
            self.assertEqual(updated["TSLA"]["start"], "2025-04-14")
            with patch("yahoo_finance_api.yf.download", return_value=frame[COLUMNS]) as download:
                retrieve_daily_prices("TSLA", now=NOW, cache_dir=root)
            self.assertEqual(download.call_args.kwargs["start"].isoformat(), "2026-10-02")
            before = {file.name: (file.read_bytes(), file.stat().st_mtime_ns) for file in root.iterdir()}
            self.assertEqual(migrate_caches(root, now=NOW)["unchanged"], 1)
            self.assertEqual(before, {file.name: (file.read_bytes(), file.stat().st_mtime_ns) for file in root.iterdir()})
            self.assertEqual(alert.read_bytes(), alert_before)

    def test_legacy_column_order_and_bad_rsi_are_derived_only(self):
        raw = prices(True)[["Close", "High", "Low", "Open", "Volume"]]
        raw["RSI"] = "invalid"
        text = raw.to_csv(index_label="Date", float_format="%.17g")
        output = enrich_price_csv(text, "TSLA", NOW.date())
        new = pd.read_csv(io.StringIO(output), index_col=0, float_precision="round_trip")
        np.testing.assert_array_equal(new[COLUMNS], raw[COLUMNS])
        np.testing.assert_array_equal(new["RSI"], rsi(raw[COLUMNS].copy())["RSI"])

    @patch("yahoo_finance_api.yf.download")
    def test_enriched_cache_reruns_overlap_corrections_and_failed_downloads(self, download):
        with tempfile.TemporaryDirectory() as directory:
            data = prices(True)
            # An oscillating series ensures corrections change RSI across history.
            close = 150 + np.sin(np.arange(len(data)) / 3) * 15 + np.arange(len(data)) / 20
            for field in ("Open", "Close"): data[field] = close
            data["High"], data["Low"] = close + 2, close - 2
            download.return_value = data
            first = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            path = Path(directory) / "TSLA.csv"
            state = Path(directory) / "price_cache_state.json"
            before = (path.read_bytes(), path.stat().st_mtime_ns, state.read_bytes())
            retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns, state.read_bytes()))
            self.assertEqual(download.call_args.kwargs["start"].isoformat(), "2026-10-02")
            self.assertEqual(json.loads(state.read_text())["TSLA"]["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            old_rsi = pd.read_csv(path)["RSI"].to_numpy()
            corrected = data.copy()
            corrected.iloc[100:140, corrected.columns.get_indexer(["Open", "High", "Low", "Close"])] *= .8
            download.return_value = corrected
            # Force the ordinary full-history integrity check, as on a new session.
            state.unlink()
            result = retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            cached = pd.read_csv(path, index_col=0, float_precision="round_trip")
            np.testing.assert_array_equal(cached["RSI"], rsi(result.copy())["RSI"])
            self.assertFalse(np.allclose(old_rsi[140:], cached["RSI"].to_numpy()[140:]))
            before_failure = path.read_bytes(), state.read_bytes()
            download.side_effect = RuntimeError("provider down")
            retrieve_daily_prices("TSLA", now=NOW, cache_dir=directory)
            self.assertEqual(before_failure, (path.read_bytes(), state.read_bytes()))
            self.assertEqual(first.columns.tolist(), COLUMNS)

    def test_corrupt_files_are_preserved_nonprices_ignored_and_other_caches_migrate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = prices(True).to_csv(index_label="Date")
            (root / "TSLA.csv").write_text(good)
            (root / "notes.csv").write_text("ticker,note\nTSLA,research\n")
            (root / "BAD.csv").write_text("Date,Open,High,Low,Close,Volume\n2026-10-16,-1,1,-1,0,2\n")
            metadata = root / "price_cache_state.json"
            metadata.write_text("{invalid-json")
            bad = (root / "BAD.csv").read_bytes()
            result = migrate_caches(root, now=NOW)
            self.assertEqual(result["migrated"], 1)
            self.assertEqual(result["ignored"], 1)
            self.assertIn("BAD.csv", result["errors"])
            self.assertIn("price_cache_state.json", result["errors"])
            self.assertEqual(metadata.read_text(), "{invalid-json")
            self.assertEqual(bad, (root / "BAD.csv").read_bytes())
            for text in (good + good.splitlines()[1] + "\n", good.replace("2026-10-16", "2026-10-19")):
                with self.assertRaises(ValueError):
                    enrich_price_csv(text, "TSLA", NOW.date())

    def test_untrusted_metadata_is_not_promoted_to_reconciled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "TSLA.csv").write_text(prices(True).to_csv(index_label="Date"))
            state = root / "price_cache_state.json"
            state.write_text(json.dumps({"TSLA": {"sha256": "a" * 64, "full_session": "2026-10-16"}}))
            migrate_caches(root, now=NOW)
            self.assertEqual(json.loads(state.read_text())["TSLA"]["sha256"], "a" * 64)


class HistoricalSignalTests(unittest.TestCase):
    def test_thresholds_alignment_first_entries_and_missing_history(self):
        values = [None, 29, 30, 31, 69, 70, 75, None, 29, 29, 50, 70]
        data = pd.DataFrame({"Close": np.arange(len(values)) + 100., "RSI": values}, index=pd.date_range("2026-01-01", periods=len(values)))
        signals = historical_signals(data)
        self.assertEqual([row["signal"] for row in signals], ["Buy", "Buy", "Sell", "Sell", "Buy", "Buy", "Sell"])
        self.assertEqual([row["price"] for row in signals], [101, 102, 105, 106, 108, 109, 111])
        self.assertEqual(signals[0]["date"], "2026-01-02")
        entries = historical_signals(data, first_only=True)
        self.assertEqual([row["price"] for row in entries], [101, 105, 108, 111])
        self.assertEqual(historical_signals(data, lower=20, upper=80), [])


class DashboardTests(unittest.TestCase):
    def seed(self, root):
        (root / "config").mkdir()
        (root / "data").mkdir()
        securities = read_securities(Path("tests/fixtures/papertrader/securities.csv").read_text())
        save_securities(root / "config/securities.csv", securities)
        (root / "config/tickers.txt").write_text("GOOG\nBTCUSD\nMISSING\n0981.HK\n")
        (root / "config/short_watchlist.csv").write_text("ticker,mode,sector\nFCEL,active,Power\nKSCP,research_only,Robotics\n")
        for symbol in ("GOOG", "BTC-USD", "NVDA", "0981.HK"):
            # Calendar-normalize through the normal downloader before building.
            data = prices(True)
            if symbol == "BTC-USD":
                data.index += pd.Timedelta(days=1)
            with patch("yahoo_finance_api.yf.download", return_value=data):
                retrieve_daily_prices(symbol, now=NOW, cache_dir=root / "data")
        # The pure Python unit tests isolate packaging from the real ECharts browser tests.
        source = root / "assets"
        vendor = source / "node_modules/echarts"
        (vendor / "dist").mkdir(parents=True)
        (vendor / "package.json").write_text('{"version":"6.1.0"}')
        for filename in ("dist/echarts.min.js", "LICENSE", "NOTICE"):
            (vendor / filename).write_text("public test asset")
        for filename in ("index.html", "app.js", "charts.js", "style.css"):
            (source / filename).write_text("public test asset")
        return source

    @patch("dashboard.subprocess.check_output", return_value="2026-10-18T22:00:00+00:00\n")
    def test_manifest_all_identities_missing_data_aliases_and_no_secrets(self, _):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.seed(root)
            (root / "data/SECRET.txt").write_text("must never publish")
            with patch("dashboard.SITE_SOURCE", source), patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "NEVER-PUBLISH-THIS", "SITE_BASE_URL": "https://example.test/financealerts/"}):
                result = build_site(root, root / "public")
                before = {p.relative_to(root / "public"): p.read_bytes() for p in (root / "public").rglob("*") if p.is_file()}
                build_site(root, root / "public")
            self.assertEqual(before, {p.relative_to(root / "public"): p.read_bytes() for p in (root / "public").rglob("*") if p.is_file()})
            self.assertEqual(len(result["securities"]), 97)
            by_ticker = {item["ticker"]: item for item in result["securities"]}
            self.assertFalse(by_ticker["MISSING"]["available"])
            self.assertEqual(by_ticker["MISSING"]["condition"], "Unavailable")
            self.assertTrue(by_ticker["NVDA"]["available"])
            self.assertEqual(by_ticker["FCEL"]["universe"], "short")
            self.assertEqual(by_ticker["KSCP"]["universe"], "research_only")
            self.assertEqual(result["aliases"]["GOOGL"], "GOOG")
            self.assertEqual(result["aliases"]["BTCUSD"], "BTC-USD")
            self.assertEqual(result["aliases"]["0981.HK"], "0981.HK")
            self.assertEqual(result["base_url"], "https://example.test/financealerts/")
            dataset = json.loads((root / "public" / by_ticker["NVDA"]["dataset"]).read_text())
            self.assertEqual(dataset["rows"][-1][7], "Sell")
            self.assertEqual(dataset["rows"][-1][6], 100)
            self.assertEqual(dataset["rows"][-1][4], by_ticker["NVDA"]["close"])
            text = "".join(value.decode() for value in before.values())
            self.assertNotIn("NEVER-PUBLISH-THIS", text)
            self.assertNotIn(str(root), text)
            self.assertNotIn("must never publish", text)

    def test_stale_and_corrupt_data_keep_security_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self.seed(root)
            path = root / "data/GOOG.csv"
            path.write_text(path.read_text().replace(",100\n", ",bad-rsi\n"))
            # A malformed RSI column is not published as confirmed data.
            content = pd.read_csv(root / "data/NVDA.csv", index_col=0)
            content["RSI"] = 999
            content.to_csv(root / "data/NVDA.csv")
            (root / "data/TSLA.csv").write_text('Date,Open,High,Low,Close,Volume\n"broken')
            with patch("dashboard.SITE_SOURCE", source):
                result = build_site(root, root / "public", datetime(2026, 10, 20, 22, tzinfo=timezone.utc))
            items = {item["ticker"]: item for item in result["securities"]}
            self.assertFalse(items["NVDA"]["available"])
            self.assertIn("migration", items["NVDA"]["diagnostic"])
            self.assertFalse(items["TSLA"]["available"])
            self.assertIn("unavailable", items["TSLA"]["diagnostic"])
            self.assertTrue(items["0981.HK"]["available"])
            self.assertTrue(items["0981.HK"]["stale"])
            self.assertIn("Stale", items["0981.HK"]["diagnostic"])

    def test_telegram_all_directions_preserve_links_state_and_encoded_provider(self):
        for direction in ("Buy", "Sell", "Short"):
            row = candidate("0981.HK", direction=direction, rsi=75, research_status="pending")
            parser = Links()
            parser.feed(ticker_line(row))
            self.assertEqual(len(parser.links), 3)
            self.assertIn("tradingview.com", parser.links[0])
            self.assertIn("/securities/security_", parser.links[1])
            self.assertEqual(parser.links[2], "https://stell0.github.io/financealerts/?ticker=0981.HK")
            before = bar_identity(row)
            row["bar"]["RSI"] = 99
            self.assertEqual(bar_identity(row), before)
        with patch.dict(os.environ, {"SITE_BASE_URL": "https://example.test/custom/"}):
            self.assertEqual(chart_url(MonitoredTicker("BTCUSD", "BTC-USD")), "https://example.test/custom/?ticker=BTC-USD")
        for invalid in ("file:///tmp/site", "https://user:password@example.test", "https://example.test/?token=secret"):
            with patch.dict(os.environ, {"SITE_BASE_URL": invalid}), self.assertRaises(ValueError):
                site_base_url()
