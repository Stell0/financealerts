"""FinanceAlerts-owned adjusted daily prices and exchange-session-aware caching."""

import csv
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from io import StringIO
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import yfinance as yf
from indicators import rsi

COLUMNS = ["Open", "High", "Low", "Close", "Volume"]
CALENDARS = {"XNAS": "XNYS", "XOTC": "XNYS", "XKOS": "XKRX", "XOFF": "24/7"}
SUFFIXES = {
    ".L": "XLON",
    ".AX": "XASX",
    ".PA": "XPAR",
    ".F": "XFRA",
    ".VI": "XWBO",
    ".HK": "XHKG",
    ".KQ": "XKRX",
    ".KS": "XKRX",
    ".AS": "XAMS",
    ".DE": "XETR",
    ".MI": "XMIL",
}


def _sanitize_ticker_filename(ticker):
    return "".join("_" if char in '/\\:*?"<>|' else char for char in ticker)


def calendar_name(ticker, venue_mic=None):
    if ticker == "BTC-USD":
        return "24/7"
    if venue_mic:
        return CALENDARS.get(venue_mic, venue_mic)
    for suffix, name in SUFFIXES.items():
        if ticker.endswith(suffix):
            return name
    if "." in ticker and not ticker.endswith((".A", ".B")):
        raise ValueError(
            f"Unknown calendar for {ticker}; register its venue in PaperTrader"
        )
    return "XNYS"


@lru_cache(maxsize=20)
def _calendar(name):
    return xcals.get_calendar(name)


def latest_completed_session(ticker, now=None, venue_mic=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone-aware")
    now = now.astimezone(timezone.utc)
    calendar = _calendar(calendar_name(ticker, venue_mic))
    sessions = calendar.sessions_in_range(
        (now.date() - timedelta(days=14)).isoformat(), now.date().isoformat()
    )
    completed = [
        session
        for session in sessions
        if calendar.session_close(session) <= pd.Timestamp(now)
    ]
    if not completed:
        raise ValueError(f"No completed session for {ticker}")
    return completed[-1].date()


def normalize_prices(frame, ticker, completed, venue_mic=None):
    frame = frame.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    if frame.empty:
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="Date"))
    if not set(COLUMNS).issubset(frame.columns):
        raise ValueError(f"Missing OHLCV columns for {ticker}")
    frame = frame[COLUMNS]
    index = pd.to_datetime(frame.index, errors="coerce")
    if index.tz is not None:
        index = index.tz_localize(None)
    frame.index = index.normalize()
    frame = frame.loc[~frame.index.isna()]
    frame = frame.loc[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.loc[np.isfinite(frame).all(axis=1)]
    valid = (
        (frame[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
        & (frame["Volume"] >= 0)
        & (frame["High"] >= frame[["Open", "Close", "Low"]].max(axis=1) - 1e-7)
        & (frame["Low"] <= frame[["Open", "Close", "High"]].min(axis=1) + 1e-7)
    )
    if not valid.all():
        logging.warning("%s: discarding invalid OHLCV rows", ticker)
    frame = frame.loc[valid & (frame.index.date <= completed)]
    if not frame.empty:
        calendar = _calendar(calendar_name(ticker, venue_mic))
        sessions = calendar.sessions_in_range(frame.index.min(), frame.index.max())
        frame = frame.loc[
            frame.index.isin(
                sessions.tz_localize(None) if sessions.tz is not None else sessions
            )
        ]
    frame.index.name = "Date"
    return frame.astype(float)


def _atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content)
    temporary.replace(path)


def enrich_price_csv(content, ticker, completed, venue_mic=None):
    """Validate all stored rows and append derived RSI without changing OHLCV text."""
    rows = list(csv.reader(StringIO(content), strict=True))
    if (
        not rows or not rows[0] or rows[0][0] != "Date"
        or len(rows[0]) != len(set(rows[0]))
        or set(rows[0]) not in ({"Date", *COLUMNS}, {"Date", *COLUMNS, "RSI"})
    ):
        raise ValueError("Expected Date,Open,High,Low,Close,Volume[,RSI]")
    if any(len(row) != len(rows[0]) for row in rows[1:]):
        raise ValueError("Malformed price cache row")
    raw = pd.read_csv(StringIO(content), index_col=0, float_precision="round_trip")
    prices = normalize_prices(raw, ticker, completed, venue_mic)
    dates = [row[0] for row in rows[1:]]
    if prices.empty or dates != prices.index.strftime("%Y-%m-%d").tolist():
        raise ValueError("Cache has invalid, duplicate, unordered or incomplete/non-session rows")
    values = rsi(prices.copy())["RSI"]
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Date", *COLUMNS, "RSI"])
    positions = [rows[0].index(field) for field in ["Date", *COLUMNS]]
    for row, value in zip(rows[1:], values):
        writer.writerow([
            *[row[index] for index in positions],
            format(value, ".17g") if np.isfinite(value) else "",
        ])
    return output.getvalue()


def migrate_caches(cache_dir="data", securities=(), now=None):
    """One local pass, no downloads; invalid files survive untouched and are reported."""
    now = now or datetime.now(timezone.utc)
    cache_dir = Path(cache_dir)
    metadata_path = cache_dir / "price_cache_state.json"
    metadata_valid = True
    result = {"migrated": 0, "unchanged": 0, "ignored": 0, "errors": {}}
    try:
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        if not isinstance(metadata, dict):
            raise ValueError("Invalid price cache metadata")
    except (OSError, ValueError) as error:
        metadata, metadata_valid = {}, False
        result["errors"][metadata_path.name] = str(error)
        logging.error("Preserving invalid cache metadata: %s", error)
    venues = {row["provider_symbol"]: row.get("venue_mic") for row in securities}
    venues["GOOG"] = venues.get("GOOGL")
    for path in sorted(cache_dir.glob("*.csv")):
        try:
            content = path.read_text()
            header = next(csv.reader(StringIO(content)), [])
            if "Date" not in header or not set(COLUMNS).intersection(header):
                result["ignored"] += 1
                continue
            ticker = path.stem
            completed = latest_completed_session(ticker, now, venues.get(ticker))
            enriched = enrich_price_csv(content, ticker, completed, venues.get(ticker))
            if enriched == content:
                result["unchanged"] += 1
                continue
            _atomic_text(path, enriched)
            previous = metadata.get(ticker)
            if (isinstance(previous, dict) and previous.get("sha256")
                    == hashlib.sha256(content.encode()).hexdigest()):
                previous["sha256"] = hashlib.sha256(enriched.encode()).hexdigest()
            result["migrated"] += 1
        except (OSError, ValueError, TypeError, csv.Error) as error:
            result["errors"][path.name] = str(error)
            logging.error("Preserving invalid cache %s: %s", path.name, error)
    if metadata_valid and metadata_path.exists():
        _atomic_text(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return result


def _has_nonpositive_prices(frame):
    columns = frame.columns.get_level_values(0)
    prices = frame.loc[:, columns.isin(COLUMNS[:-1])].apply(pd.to_numeric, errors="coerce")
    return prices.le(0).any(axis=None)


def retrieve_daily_prices(
    ticker,
    period=None,
    start=None,
    end=None,
    *,
    now=None,
    venue_mic=None,
    cache_dir="data",
):
    now = now or datetime.now(timezone.utc)
    completed = latest_completed_session(ticker, now, venue_mic)
    end_date = (
        min(pd.Timestamp(end).date(), completed + timedelta(days=1))
        if end is not None
        else completed + timedelta(days=1)
    )
    history_days = period if isinstance(period, int) else 550
    first_date = (
        pd.Timestamp(start).date()
        if start is not None
        else completed - timedelta(days=history_days)
    )
    cache_dir = Path(cache_dir)
    cache = cache_dir / f"{_sanitize_ticker_filename(ticker)}.csv"
    metadata_path = cache_dir / "price_cache_state.json"
    try:
        metadata = json.loads(metadata_path.read_text())
        if not isinstance(metadata, dict):
            metadata = {}
    except (OSError, ValueError):
        metadata = {}
    cached = pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="Date"))
    cache_hash = ""
    if cache.exists():
        try:
            content = cache.read_text()
            cached = normalize_prices(
                pd.read_csv(StringIO(content), index_col=0, float_precision="round_trip"),
                ticker,
                completed,
                venue_mic,
            )
            cache_hash = hashlib.sha256(content.encode()).hexdigest()
        except (ValueError, TypeError) as error:
            logging.warning("%s: ignoring invalid cache: %s", ticker, error)
    previous = metadata.get(ticker, {})
    full_refresh = (
        not isinstance(previous, dict)
        or previous.get("sha256") != cache_hash
        or previous.get("full_session") != completed.isoformat()
        or previous.get("start") != first_date.isoformat()
        or cached.empty
    )
    # Reconcile the retained adjusted history once per completed session. This also
    # incorporates split/dividend back-adjustments and historical corrections.
    fetch_start = (
        first_date if full_refresh else max(first_date, completed - timedelta(days=14))
    )
    download_options = dict(
        end=end_date, progress=False, auto_adjust=True, timeout=30, threads=False
    )
    try:
        fresh = yf.download(ticker, start=fetch_start, **download_options)
        if _has_nonpositive_prices(fresh):
            logging.warning(
                "%s: nonpositive adjusted prices; retrying full history with Yahoo repair",
                ticker,
            )
            fresh = yf.download(ticker, start=first_date, repair=True, **download_options)
            full_refresh = True
            if _has_nonpositive_prices(fresh):
                raise ValueError("Yahoo repair still contains nonpositive adjusted prices")
        fresh = normalize_prices(fresh, ticker, completed, venue_mic)
        if fresh.empty:
            raise ValueError("Yahoo Finance returned no valid completed bars")
    except Exception as error:
        if not cached.empty and cached.index[-1].date() == completed:
            logging.warning(
                "%s: provider unavailable; retaining completed cached bar: %s",
                ticker,
                error,
            )
            return cached
        raise ValueError(f"{ticker}: daily prices unavailable: {error}") from error
    if full_refresh and not cached.empty:
        retained = cached.loc[cached.index.date >= first_date]
        shared = retained.index.intersection(fresh.index)
        missing = retained.index.difference(fresh.index)
        if len(missing):
            old = retained.loc[shared, ["Open", "High", "Low", "Close"]].to_numpy()
            new = fresh.loc[shared, ["Open", "High", "Low", "Close"]].to_numpy()
            if not len(shared) or not np.allclose(old, new, rtol=1e-8, atol=1e-8):
                raise ValueError(
                    f"{ticker}: incomplete adjusted-history reconciliation: "
                    f"{len(missing)} cached sessions absent from valid provider history "
                    f"and overlapping prices changed or unavailable; cache preserved, retry required"
                )
    combined = fresh if cached.empty else pd.concat([cached, fresh])
    combined = combined.loc[~combined.index.duplicated(keep="last")].sort_index()
    combined = combined.loc[
        (combined.index.date >= first_date) & (combined.index.date < end_date)
    ]
    if combined.empty or combined.index[-1].date() != completed:
        raise ValueError(f"{ticker}: missing latest completed session {completed}")
    # Quantize authoritative prices first, then calculate RSI from exactly those
    # serialized closes. Derived columns never participate in reconciliation.
    content = enrich_price_csv(
        combined.astype(float).to_csv(float_format="%.10g"), ticker, completed, venue_mic
    )
    _atomic_text(cache, content)
    # Re-read serialized values so fingerprints and indicators are identical on reruns.
    combined = normalize_prices(
        pd.read_csv(StringIO(content), index_col=0, float_precision="round_trip"),
        ticker, completed, venue_mic
    )
    metadata[ticker] = {
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "start": first_date.isoformat(),
        "full_session": completed.isoformat()
        if full_refresh
        else previous["full_session"],
    }
    _atomic_text(metadata_path, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return combined


def retrieve_hourly_prices(ticker, period=None, start=None, end=None):
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=period or 14)
    return yf.download(ticker, start=start, end=end, interval="1h", progress=False)


def get_next_earnings_date(ticker):
    return yf.Ticker(ticker).earnings_dates
