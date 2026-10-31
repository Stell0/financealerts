import csv
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import main
from notifications import deliver, message_chunks
from papertrader_data import load_snapshot
from rating_config import short_threshold
from ratings import FUNDAMENTALS, rate, research_status
from registry import merge_universe, read_securities, read_short_watchlist, synchronize
from test_notifications import Links, candidate
from test_ratings import assessment, frame, supporting_assessment
from test_scan import prices

NOW = datetime(2026, 10, 18, 22, tzinfo=timezone.utc)
WATCHLIST = Path("config/short_watchlist.csv").resolve()


def security(ticker, **changes):
    return {
        "security_id": "security_" + ticker,
        "ticker": ticker,
        "provider_symbol": ticker,
        "company_name": ticker + " Company",
        "venue_mic": "XNAS",
        "currency": "USD",
        "instrument_type": "equity",
        "research_page": f"data/wiki/securities/security_{ticker}.md",
        **changes,
    }


def local(ticker, mode="active"):
    return {"ticker": ticker, "mode": mode, "sector": "Test sector"}


def short_row(ticker="FCEL", **changes):
    return candidate(
        ticker, **{"direction": "Short", "rsi": 76.4, "research_status": "current", **changes}
    )


class ShortRegistryTests(unittest.TestCase):
    def test_initial_watchlist(self):
        rows = read_short_watchlist(WATCHLIST)
        self.assertEqual(
            [row["ticker"] for row in rows if row["mode"] == "active"],
            ["FCEL","AI","SPCE","CIFR","WULF","BBAI","APLD","ONDS","AEVA","PDYN","CRML","ENVX","EOSE","LCID","LWLG","NPWR","POET","RZLV"].copy(),
        )
        self.assertEqual(
            [row["ticker"] for row in rows if row["mode"] == "research_only"],
            ["KSCP","MVIS","PSNY","PLUG","ARQQ","SPIR","ARBE","BLNK","CHPT","DVLT","EVEX","EVTL","LIDR","NVTS","VERI","WATT"].copy(),
        )

    def test_invalid_watchlist_fails_explicitly(self):
        invalid = [
            "ticker,mode\nFCEL,active\n",
            "ticker,mode,sector\nFCEL,enabled,Hydrogen\n",
            "ticker,mode,sector\n../BAD,active,Hydrogen\n",
            "ticker,mode,sector\nFCEL,active,\n",
            "ticker,mode,sector\nFCEL,active\n",
            "ticker,mode,sector\nFCEL,active,Hydrogen,extra\n",
            "ticker,mode,sector\nFCEL,active,Hydrogen\nfcel,research_only,H\n",
            "ticker,mode,sector\nGOOG,active,AI\nGOOGL,active,AI\n",
            'ticker,mode,sector\nFCEL,active,"Hydrogen\n',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.csv"
            for text in invalid:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises((ValueError, csv.Error)):
                        read_short_watchlist(path)
            with self.assertRaises(FileNotFoundError):
                read_short_watchlist(Path(directory) / "missing.csv")

    def test_old_and_new_snapshots_exclude_all_watchlist_tickers_from_saved_longs(self):
        rows = read_short_watchlist(WATCHLIST)
        for new_schema in (False, True):
            with self.subTest(new_schema=new_schema), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                tables = root / "data/tables"
                tables.mkdir(parents=True)
                securities = [security("LONG")]
                for row in rows:
                    entry = security(row["ticker"])
                    if new_schema:
                        entry["research_role"] = (
                            "short_candidate" if row["mode"] == "active" else "short_research_only"
                        )
                    securities.append(entry)
                if new_schema:
                    securities[0]["research_role"] = "long"
                with (tables / "securities.csv").open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=securities[0].keys())
                    writer.writeheader()
                    writer.writerows(securities)
                imported, text = load_snapshot(directory=root)
                self.assertEqual(text, "")
                path = root / "tickers.txt"
                # Also clean up an earlier accidental long import.
                path.write_text("LONG\nFCEL\nKSCP\n")
                universe = synchronize(path, "FCEL AI KSCP LONG", imported, short_watchlist=rows)
                self.assertEqual(path.read_text(), "LONG\n")
                self.assertEqual(len(universe), len(rows) + 1)
                self.assertEqual(sum(item.universe == "short" for item in universe), sum(row["mode"] == "active" for row in rows))
                self.assertEqual(sum(item.universe == "research_only" for item in universe), sum(row["mode"] == "research_only" for row in rows))
                before = path.read_bytes(), path.stat().st_mtime_ns
                self.assertEqual(
                    universe, synchronize(path, "FCEL", imported, short_watchlist=rows)
                )
                self.assertEqual(before, (path.read_bytes(), path.stat().st_mtime_ns))

    def test_papertrader_roles_cannot_enable_short_alerts(self):
        securities = [
            security("LONG"),
            security("ACTIVE", research_role="short_candidate"),
            security("RESEARCH", research_role="short_research_only"),
        ]
        universe = merge_universe(["ACTIVE", "RESEARCH"], "ACTIVE", securities)
        self.assertEqual(
            {item.ticker: item.universe for item in universe},
            {"ACTIVE": "research_only", "LONG": "long", "RESEARCH": "research_only"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tickers.txt"
            synchronize(path, "ACTIVE RESEARCH", securities)
            self.assertEqual(path.read_text(), "LONG\n")
            for symbol in ("ACTIVE", "RESEARCH"):
                self.assertEqual(
                    synchronize(path, "", securities, override=symbol)[0].universe,
                    "research_only",
                )
        overridden = merge_universe(
            [], "", securities, [local("ACTIVE", "research_only"), local("RESEARCH")]
        )
        self.assertEqual(
            {item.ticker: item.universe for item in overridden},
            {"ACTIVE": "research_only", "LONG": "long", "RESEARCH": "short"},
        )

    def test_alias_identity_exchange_and_override_classification(self):
        securities = [
            security("GOOGL"),
            security("LOCAL", provider_symbol="LOCAL.PA", venue_mic="XPAR"),
            security("LOCAL.F", venue_mic="XFRA", currency="EUR"),
        ]
        shorts = [local("GOOGL"), local("LOCAL")]
        universe = merge_universe(["GOOG", "LOCAL.PA"], "GOOGL LOCAL", securities, shorts)
        self.assertEqual(len(universe), 3)
        by_symbol = {item.ticker: item for item in universe}
        self.assertEqual(by_symbol["GOOG"].universe, "short")
        self.assertEqual(by_symbol["GOOG"].yahoo_symbol, "GOOG")
        self.assertEqual(by_symbol["LOCAL.PA"].universe, "short")
        self.assertEqual(by_symbol["LOCAL.F"].universe, "long")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tickers.txt"
            path.write_text("GOOG\nLOCAL.PA\n")
            selected = synchronize(path, "", securities, "GOOGL", shorts)
            self.assertEqual(selected[0].universe, "short")
            self.assertEqual(selected[0].yahoo_symbol, "GOOGL")
            self.assertEqual(path.read_text(), "LOCAL.F\n")
        with self.assertRaisesRegex(ValueError, "Duplicate short watchlist identity"):
            merge_universe([], "", securities, [local("LOCAL"), local("LOCAL.PA")])
        ambiguous = [*securities, security("LOCAL", provider_symbol="OTHER.PA")]
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            merge_universe([], "", ambiguous, shorts)

    def test_invalid_papertrader_research_roles_fail_closed(self):
        for role in ("", "short", "unknown"):
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, "research_role"):
                read_securities(
                    ",".join(security("FCEL", research_role=role)) + "\n"
                    + ",".join(security("FCEL", research_role=role).values()) + "\n"
                )


class ShortSignalTests(unittest.TestCase):
    @patch("main.yf.Ticker")
    @patch("main.yahoo_finance_api.retrieve_daily_prices", return_value=prices(True))
    def test_local_active_candidate_before_papertrader_import(self, retrieve, ticker):
        ticker.return_value.get_info.return_value = {
            "symbol": "FCEL", "exchange": "NCM", "longName": "FuelCell Energy",
        }
        universe = merge_universe([], "FCEL", [], [local("FCEL")])
        rows, failures = main.scan(universe, {}, NOW)
        self.assertEqual(failures, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "Short")
        self.assertEqual(rows[0]["research_status"], "pending")
        message = list(message_chunks(rows))[0][0]
        self.assertIn("NASDAQ%3AFCEL", message)
        self.assertIn("/security-catalog", message)
        retrieve.assert_called_once()

    def test_long_signals_and_strict_short_rsi_threshold(self):
        for universe, rsi, expected in [
            ("long", 25, "Buy"), ("long", 75, "Sell"),
            ("short", 25, None), ("short", 65, None), ("short", 66, None),
            ("short", 69, None), ("short", 69.999, None),
            ("short", 70, "Short"), ("short", 75, "Short"),
            ("research_only", 25, None), ("research_only", 75, None),
        ]:
            with self.subTest(universe=universe, rsi=rsi):
                data = frame(rsi)
                data["Close"] = 109
                data["MACD"] = -2
                data["MACD_SIGNAL"] = -1
                data["MACD_HIST"] = [1, -0.5]
                data["SMA200"] = 110
                self.assertEqual(
                    rate(data, supporting_assessment("Sell", 10), NOW, universe=universe)[0],
                    expected,
                )
        self.assertEqual(
            rate(frame(75), now=NOW, universe="short")[1]["Short"],
            rate(frame(75), now=NOW)[1]["Sell"],
        )

    def test_short_threshold_is_independent_and_validated(self):
        with patch.dict(os.environ, {"SHORT_RSI_UPPER": "80", "RSI_upper": "60"}):
            self.assertIsNone(rate(frame(75), now=NOW, universe="short")[0])
            self.assertEqual(rate(frame(80), now=NOW, universe="short")[0], "Short")
            self.assertEqual(rate(frame(75), now=NOW)[0], "Sell")
        for invalid in ("nan", "inf", "-1", "101", "wrong"):
            with patch.dict(os.environ, {"SHORT_RSI_UPPER": invalid}):
                with self.assertRaises(ValueError):
                    short_threshold()

    def test_research_status_and_stale_rating_penalty(self):
        for research, expected in [
            (None, "pending"),
            (assessment(), "current"),
            (assessment(expires_at="2026-10-18T22:00:00Z"), "stale"),
            (assessment(expires_at="bad"), "unsupported"),
            (assessment(assessed_at="2027-01-01T00:00:00Z"), "unsupported"),
            (assessment(**dict.fromkeys(FUNDAMENTALS, "")), "unsupported"),
            (assessment(valuation_score="nan"), "partial"),
        ]:
            with self.subTest(expected=expected):
                self.assertEqual(research_status(research, NOW), expected)
                direction, scores = rate(frame(80), research, NOW, universe="short")
                self.assertEqual(direction, "Short")
                message = list(message_chunks([short_row(research_status=expected)]))[0][0]
                self.assertIn(f"Research: {expected}", message)
                if expected == "stale":
                    self.assertLessEqual(scores["Short"], 5)

    @patch("main.yahoo_finance_api.retrieve_daily_prices")
    def test_scan_once_skip_research_acquired_and_isolate_failures(self, retrieve):
        securities = [security(ticker) for ticker in ("FCEL", "LOW", "KSCP", "FAIL", "LONG")]
        securities.append(security("GONE", status="acquired"))
        shorts = [local("FCEL"), local("LOW"), local("KSCP", "research_only"), local("GONE")]
        universe = merge_universe(["FCEL"], "FCEL LOW", securities, shorts)

        def provider(symbol, **kwargs):
            if symbol == "FAIL":
                raise ValueError("provider failed")
            return prices(symbol != "LOW")

        retrieve.side_effect = provider
        rows, failures = main.scan(universe, {}, NOW)
        self.assertEqual(failures, ["FAIL"])
        self.assertEqual(
            [(row["item"].ticker, row["direction"]) for row in rows],
            [("FCEL", "Short"), ("LONG", "Sell")],
        )
        self.assertEqual(retrieve.call_count, 4)
        self.assertEqual(rows[0]["rsi"], 100)
        self.assertEqual(rows[0]["research_status"], "pending")


class ShortNotificationTests(unittest.TestCase):
    def test_html_sorting_unicode_splitting_and_independent_state(self):
        rows = [candidate("LONG"), candidate("SELL", direction="Sell")]
        rows += [short_row(f"S{i:03}", score=9 - i % 3) for i in reversed(range(40))]
        for row in rows[2:]:
            row["item"].security["company_name"] = 'Research <A&B> 🛰️🚀 "Inc."'
        chunks = list(message_chunks(rows, limit=1000))
        self.assertGreater(len(chunks), 1)
        included = [row for _, entries in chunks for row in entries]
        self.assertEqual(included[:2], rows[:2])
        self.assertEqual(
            included[2:],
            sorted(rows[2:], key=lambda row: (-row["score"], row["item"].ticker)),
        )
        for message, entries in chunks:
            self.assertLessEqual(len(message.encode("utf-16-le")) // 2, 1000)
            links = Links()
            links.feed(message)
            self.assertEqual(len(links.links), 2 * len(entries))
            if any(row["direction"] == "Short" for row in entries):
                self.assertIn("<b>Short Watch — Put Candidates</b>", message)
                self.assertIn("RSI 76.4 | Research: current", message)
                self.assertIn("Research &lt;A&amp;B&gt;", message)
        with self.assertRaisesRegex(ValueError, "exceeds Telegram"):
            list(message_chunks([short_row()], limit=20))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            short = short_row()
            sell = candidate("FCEL", direction="Sell")
            self.assertEqual(deliver([sell], path, lambda _: True), 1)
            self.assertEqual(deliver([short], path, lambda _: True), 1)
            self.assertEqual(deliver([short, sell], path, lambda _: True), 0)
            self.assertEqual(
                set(json.loads(path.read_text())["delivered"]), {"FCEL:Sell", "FCEL:Short"}
            )
            short["score"] = 2
            short["research_status"] = "stale"
            self.assertEqual(deliver([short], path, lambda _: True), 0)
            short["bar"]["Volume"] += 1
            self.assertEqual(deliver([short], path, lambda _: True), 1)
            self.assertEqual(deliver([sell], path, lambda _: True), 0)

    def test_short_partial_delivery_retry(self):
        rows = [short_row(f"S{i:03}") for i in range(40)]
        chunks = list(message_chunks(rows))
        self.assertGreater(len(chunks), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            calls = []

            def send(message):
                calls.append(message)
                if len(calls) == 2:
                    raise RuntimeError("send failed")
                return True

            with self.assertRaises(RuntimeError):
                deliver(rows, path, send)
            successful = len(chunks[0][1])
            self.assertEqual(len(json.loads(path.read_text())["delivered"]), successful)
            self.assertEqual(deliver(rows, path, lambda _: True), len(rows) - successful)
            self.assertEqual(deliver(rows, path, lambda _: True), 0)


class ShortConsoleIntegrationTests(unittest.TestCase):
    @patch("yahoo_finance_api.yf.download")
    def test_console_cli_all_watchlist_tickers_no_telegram_or_long_contamination(self, download):
        watchlist = read_short_watchlist(WATCHLIST)
        securities = [security("LONGBUY"), security("LONGSELL")]
        securities += [
            security(row["ticker"], research_role=(
                "short_candidate" if row["mode"] == "active" else "short_research_only"
            )) for row in watchlist
        ]
        securities[0]["research_role"] = securities[1]["research_role"] = "long"

        def provider(symbol, **kwargs):
            data = prices(symbol != "LONGBUY")
            return data.loc[
                (data.index.date >= kwargs["start"]) & (data.index.date < kwargs["end"])
            ]

        download.side_effect = provider
        scan = main.scan
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/short_watchlist.csv").write_bytes(WATCHLIST.read_bytes())
            (root / "config/tickers.txt").write_text("FCEL\nLONGBUY\n")
            tables = root / "PaperTrader/data/tables"
            tables.mkdir(parents=True)
            with (tables / "securities.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=securities[0].keys())
                writer.writeheader()
                writer.writerows(securities)
            previous = Path.cwd()
            try:
                os.chdir(root)
                with (
                    patch.dict(os.environ, {
                        "PAPERTRADER_DIR": str(root / "PaperTrader"),
                        "TICKER_LIST": "FCEL KSCP",
                    }, clear=True),
                    patch("main.scan", side_effect=lambda universe, assessments: scan(
                        universe, assessments, NOW
                    )),
                    patch("telegram_alert.telegram.Bot") as bot,
                    redirect_stdout(io.StringIO()) as output,
                ):
                    self.assertEqual(main.main([]), 0)
                    first = output.getvalue()
                    self.assertIn("<b>Buy:</b>", first)
                    self.assertIn("<b>Sell:</b>", first)
                    self.assertIn("<b>Short Watch — Put Candidates</b>", first)
                    self.assertIn("RSI 100.0 | Research: pending", first)
                    self.assertEqual(first.count(">FCEL</a>"), 1)
                    self.assertNotIn(">KSCP</a>", first)
                    self.assertEqual(
                        (root / "config/tickers.txt").read_text(), "LONGBUY\nLONGSELL\n"
                    )
                    self.assertFalse((root / "data/alert_state.json").exists())
                    bot.assert_not_called()
                    self.assertEqual(download.call_count, 18 + 2)
                    output.seek(0)
                    output.truncate()
                    self.assertEqual(main.main([]), 0)
                    self.assertEqual(output.getvalue(), first)
                    self.assertFalse((root / "data/alert_state.json").exists())
                    self.assertEqual(len(list((root / "data").glob("*.csv"))), 18 + 2)
            finally:
                os.chdir(previous)
