"""Compact linked reports and successful-delivery identities based only on OHLCV."""

import hashlib
import html
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote, urlencode

import telegram_alert
from ratings import stars
from site_config import chart_url

BASE_URL = "https://kabutojira.github.io/PaperTrader"
EXCHANGES = {
    "XNAS": "NASDAQ",
    "XNYS": "NYSE",
    "XOTC": "OTC",
    "XLON": "LSE",
    "XASX": "ASX",
    "XPAR": "EURONEXT",
    "XAMS": "EURONEXT",
    "XFRA": "FWB",
    "XETR": "XETR",
    "XWBO": "VIE",
    "XHKG": "HKEX",
    "XKOS": "KRX",
    "XMIL": "MIL",
}
YAHOO_EXCHANGES = {
    "NMS": "XNAS",
    "NGM": "XNAS",
    "NCM": "XNAS",
    "NYQ": "XNYS",
    "ASE": "XNYS",
    "PCX": "XNYS",
    "PNK": "XOTC",
    "OQB": "XOTC",
    "PAR": "XPAR",
    "AMS": "XAMS",
    "GER": "XETR",
    "FRA": "XFRA",
    "LSE": "XLON",
    "ASX": "XASX",
    "HKG": "XHKG",
    "KOE": "XKOS",
    "VIE": "XWBO",
    "MIL": "XMIL",
}


def tradingview_url(item):
    if item.yahoo_symbol == "BTC-USD":
        chart = "BITSTAMP:BTCUSD"
    else:
        security = item.security or {}
        venue = EXCHANGES.get(security.get("venue_mic"))
        if not venue:
            raise ValueError(f"No verified TradingView exchange for {item.ticker}")
        symbol = item.yahoo_symbol
        for suffix in (
            ".L",
            ".AX",
            ".PA",
            ".AS",
            ".DE",
            ".F",
            ".VI",
            ".HK",
            ".KQ",
            ".KS",
            ".MI",
        ):
            if symbol.endswith(suffix):
                symbol = symbol[: -len(suffix)]
                break
        chart = f"{venue}:{symbol}"
    return "https://www.tradingview.com/chart/?" + urlencode({"symbol": chart})


def research_url(item):
    security = item.security or {}
    sid = security.get("security_id", "")
    page = security.get("research_page", "")
    if sid and page == f"data/wiki/securities/{sid}.md":
        return f"{BASE_URL}/securities/{quote(sid, safe='')}"
    if page:
        logging.warning(
            "%s: invalid/noncanonical research page; using catalog", item.ticker
        )
    return f"{BASE_URL}/security-catalog" + (
        f"#security-{quote(sid, safe='')}" if sid else ""
    )


def ticker_line(candidate):
    item = candidate["item"]
    name = (item.security or {}).get("company_name") or item.ticker
    line = (
        f'<a href="{html.escape(tradingview_url(item), quote=True)}">{html.escape(item.ticker)}</a>'
        f" | {stars(candidate['score'])} | "
        f'<a href="{html.escape(research_url(item), quote=True)}">{html.escape(name)}</a>'
        f' | <a href="{html.escape(chart_url(item), quote=True)}">Chart</a>'
    )
    if candidate["direction"] == "Short":
        line += (
            f" | RSI {candidate['rsi']:.1f}"
            f" | Research: {html.escape(candidate['research_status'])}"
        )
    return line


def bar_identity(candidate):
    bar = candidate["bar"]
    normalized = {
        "date": candidate["date"].isoformat(),
        **{
            field: format(float(bar[field]), ".10g")
            for field in ("Open", "High", "Low", "Close", "Volume")
        },
    }
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def state_key(candidate):
    # Prices of GOOG and GOOGL are distinct even though research identity is shared.
    return f"{candidate['item'].yahoo_symbol}:{candidate['direction']}"


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {"version": 1, "delivered": {}}
    state = json.loads(path.read_text())
    if (
        not isinstance(state, dict)
        or state.get("version") != 1
        or not isinstance(state.get("delivered"), dict)
        or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or not re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in state["delivered"].items()
        )
    ):
        raise ValueError(
            "Invalid alert delivery state; restore the committed file before retrying"
        )
    return state


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def message_chunks(candidates, limit=4096):
    """Split conservatively by raw HTML UTF-16 length, always at complete ticker lines."""
    message, included, section = "", [], None
    for direction in ("Buy", "Sell", "Short"):
        rows = sorted(
            (row for row in candidates if row["direction"] == direction),
            key=lambda row: (-row["score"], row["item"].ticker),
        )
        for row in rows:
            line = ticker_line(row)
            title = (
                "Short Watch — Put Candidates" if direction == "Short" else direction + ":"
            )
            header = f"<b>{title}</b>\n"
            addition = (
                ("\n\n" if message else "") + header if section != direction else "\n"
            ) + line
            if len((message + addition).encode("utf-16-le")) // 2 > limit:
                if included:
                    yield message, included
                message, included, section = "", [], None
                addition = header + line
                if len(addition.encode("utf-16-le")) // 2 > limit:
                    raise ValueError(
                        f"Ticker line exceeds Telegram message limit: {row['item'].ticker}"
                    )
            message += addition
            included.append(row)
            section = direction
    if included:
        yield message, included


def deliver(candidates, state_path="data/alert_state.json", sender=None):
    state = load_state(state_path)
    pending = [
        row
        for row in candidates
        if state["delivered"].get(state_key(row)) != bar_identity(row)
    ]
    sent = 0
    for message, rows in message_chunks(pending):
        successful = (sender or telegram_alert.send_alert)(message)
        if successful:
            for row in rows:
                state["delivered"][state_key(row)] = bar_identity(row)
            save_state(state_path, state)
            sent += len(rows)
    return sent
