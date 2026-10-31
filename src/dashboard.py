"""Deterministic, local-only dashboard datasets from the committed registry/cache."""

import csv
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pandas as pd

from rating_config import thresholds
from registry import (
    identity_symbol, merge_universe, read_securities, read_short_watchlist, read_tickers,
)
from site_config import site_base_url
from yahoo_finance_api import (
    COLUMNS, enrich_price_csv, latest_completed_session, _sanitize_ticker_filename,
)

SITE_SOURCE = Path(__file__).resolve().parents[1] / "site"


def rsi_signal(value, lower, upper):
    if pd.isna(value):
        return None
    if value <= lower:
        return "Buy"
    if value >= upper:
        return "Sell"
    return None


def historical_signals(prices, lower=30, upper=70, first_only=False):
    """Retrospective RSI conditions only; no ratings, assessments or delivery evidence."""
    output, previous = [], None
    for date, row in prices.iterrows():
        rsi = row["RSI"]
        signal = rsi_signal(rsi, lower, upper)
        if signal and (not first_only or signal != previous):
            output.append({
                "date": date.date().isoformat(), "price": float(row["Close"]),
                "rsi": float(rsi), "signal": signal,
            })
        previous = signal
    return output


def _json(path, value):
    path.write_text(json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ) + "\n")


def build_site(root, output, now=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if (output == root or output in root.parents or
            root in output.parents and output.relative_to(root).parts[0]
            in {"src", "data", "config", ".git"}):
        raise ValueError("Site output must not overwrite source or canonical data")
    if now is None:
        stamp = subprocess.check_output(
            ["git", "-c", f"safe.directory={root}", "log", "-1", "--format=%cI"],
            cwd=root, text=True,
        ).strip()
        now = datetime.fromisoformat(stamp)
    securities = read_securities((root / "config/securities.csv").read_text())
    shorts = read_short_watchlist(root / "config/short_watchlist.csv")
    universe = merge_universe(
        read_tickers(root / "config/tickers.txt"), "", securities, shorts
    )
    lower, upper = thresholds()
    vendor = SITE_SOURCE / "node_modules/echarts"
    if json.loads((vendor / "package.json").read_text())["version"] != "6.1.0":
        raise ValueError("Install the pinned site dependencies with npm ci --prefix site")
    output.mkdir(parents=True, exist_ok=True)
    (output / "data").mkdir(exist_ok=True)
    # Only known public source files and allowlisted identity fields reach the site.
    for name in ("index.html", "app.js", "charts.js", "style.css"):
        shutil.copyfile(SITE_SOURCE / name, output / name)
    (output / "vendor").mkdir(exist_ok=True)
    for source, name in (
        ("dist/echarts.min.js", "echarts.min.js"), ("LICENSE", "LICENSE"), ("NOTICE", "NOTICE")
    ):
        shutil.copyfile(vendor / source, output / "vendor" / name)
    (output / ".nojekyll").write_text("")
    items, aliases = [], {}
    for item in universe:
        security = item.security or {}
        entry = {
            "ticker": item.ticker, "symbol": item.yahoo_symbol,
            "name": security.get("company_name", "Bitcoin" if item.yahoo_symbol == "BTC-USD" else item.ticker),
            "market": security.get("venue_mic", "XOFF" if item.yahoo_symbol == "BTC-USD" else "Unregistered"),
            "currency": security.get("currency", "USD" if item.yahoo_symbol == "BTC-USD" else ""),
            "universe": item.universe, "security_id": security.get("security_id"),
            "status": security.get("status", ""), "available": False,
            "condition": "Unavailable", "last_date": None, "close": None, "rsi": None,
            "stale": False, "diagnostic": "No committed price cache. Awaiting a successful daily scan.",
            "dataset": None,
        }
        cache = root / "data" / f"{_sanitize_ticker_filename(item.yahoo_symbol)}.csv"
        try:
            completed = latest_completed_session(item.yahoo_symbol, now, security.get("venue_mic"))
            if cache.exists():
                content = cache.read_text()
                canonical = enrich_price_csv(
                    content, item.yahoo_symbol, completed, security.get("venue_mic")
                )
                if canonical != content:
                    raise ValueError("RSI cache needs migration: run python scripts/migrate_rsi.py")
                prices = pd.read_csv(
                    StringIO(content), index_col=0, parse_dates=True,
                    float_precision="round_trip",
                )
                signals = {row["date"]: row["signal"]
                           for row in historical_signals(prices, lower, upper)}
                entries = {row["date"] for row in historical_signals(
                    prices, lower, upper, first_only=True
                )}
                rows = []
                for date, row in prices.iterrows():
                    day = date.date().isoformat()
                    values = [float(row[field]) if pd.notna(row[field]) else None
                              for field in [*COLUMNS, "RSI"]]
                    rows.append([day, *values, signals.get(day), day in entries])
                filename = hashlib.sha256(item.yahoo_symbol.encode()).hexdigest()[:20] + ".json"
                _json(output / "data" / filename, {
                    "symbol": item.yahoo_symbol,
                    "columns": ["Date", *COLUMNS, "RSI", "Signal", "Entry"], "rows": rows,
                })
                last = rows[-1]
                last_rsi = last[6]
                stale = last[0] < completed.isoformat() and entry["status"] != "acquired"
                condition = "Unavailable" if last_rsi is None else {
                    "Buy": "Oversold", "Sell": "Overbought", None: "Neutral"
                }[rsi_signal(last_rsi, lower, upper)]
                diagnostic = ""
                if stale:
                    diagnostic = (f"Stale: last available {last[0]}; "
                                  f"expected completed session {completed}.")
                elif entry["status"] == "acquired":
                    diagnostic = "Acquired security: retained historical prices."
                elif last_rsi is None:
                    diagnostic = "Insufficient completed price history for RSI(14)."
                entry.update(
                    available=True, dataset="data/" + filename, last_date=last[0],
                    close=last[4], rsi=last_rsi, stale=stale,
                    condition=condition, diagnostic=diagnostic,
                )
        except (OSError, ValueError, TypeError, csv.Error) as error:
            reason = "Cannot read committed price cache." if isinstance(error, OSError) else str(error)
            entry["diagnostic"] = f"Price dataset unavailable: {reason}"
        items.append(entry)
        for symbol in {item.ticker, item.yahoo_symbol, security.get("ticker", item.ticker)}:
            aliases.setdefault(symbol, []).append(item.yahoo_symbol)
    for alias, canonical in (("GOOG", "GOOGL"), ("BTC-USD", "BTCUSD")):
        target = next((entry["symbol"] for entry in items
                       if identity_symbol(entry["ticker"]) == canonical), None)
        if target:
            aliases[alias] = aliases[canonical] = [target]
    manifest = {
        "version": 1, "base_url": site_base_url(),
        "thresholds": {"lower": lower, "upper": upper},
        "snapshot_at": now.astimezone(timezone.utc).isoformat(),
        "data_as_of": max((entry["last_date"] for entry in items
                           if entry["last_date"]), default=None),
        "aliases": {key: values[0] for key, values in sorted(aliases.items())
                    if len(set(values)) == 1},
        "securities": items,
    }
    _json(output / "manifest.json", manifest)
    return manifest
