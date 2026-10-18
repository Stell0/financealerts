"""Additive ticker registry and immutable PaperTrader identity joins."""

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import re

SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.^=+-]{0,39}$")
SECURITY_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
ALIASES = {"GOOG": "GOOGL", "BTC-USD": "BTCUSD"}


def normalize(value):
    symbol = value.strip().upper()
    if not SYMBOL.fullmatch(symbol):
        raise ValueError(f"Invalid ticker: {value!r}")
    return symbol


def identity_symbol(symbol):
    return ALIASES.get(normalize(symbol), normalize(symbol))


def read_securities(text):
    reader = csv.DictReader(StringIO(text.lstrip('\ufeff')))
    required = {"security_id", "ticker", "provider_symbol", "company_name", "venue_mic", "currency", "instrument_type", "research_page"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("PaperTrader securities CSV lacks required identity columns")
    rows, ids, providers = [], set(), set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Malformed PaperTrader security row")
        row = {key: value.strip() for key, value in row.items()}
        sid = row["security_id"]
        if not SECURITY_ID.fullmatch(sid) or sid in ids:
            raise ValueError(f"Invalid or duplicate security_id: {sid!r}")
        for field in ("ticker", "provider_symbol"):
            row[field] = normalize(row[field])
        key = (row["provider_symbol"], row["venue_mic"], row["currency"])
        if key in providers or not row["company_name"]:
            raise ValueError(f"Duplicate or incomplete identity: {sid}")
        ids.add(sid)
        providers.add(key)
        rows.append(row)
    return rows


def read_tickers(path):
    if not Path(path).exists():
        return []
    return [normalize(line) for line in Path(path).read_text().splitlines() if line.strip()]


@dataclass(frozen=True)
class MonitoredTicker:
    ticker: str
    yahoo_symbol: str
    security: dict | None = None

    @property
    def identity(self):
        return self.security["security_id"] if self.security else identity_symbol(self.ticker)


def resolve(symbol, securities):
    symbol = normalize(symbol)
    canonical = identity_symbol(symbol)
    matches = [row for row in securities if canonical in {
        identity_symbol(row["ticker"]), identity_symbol(row["provider_symbol"])
    }]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous PaperTrader identity for {symbol}")
    security = matches[0] if matches else None
    yahoo = ("GOOG" if symbol == "GOOG" else security["provider_symbol"]) if security else symbol
    if canonical == "BTCUSD":
        yahoo = "BTC-USD"
    # Use provider-qualified symbols for exchanges where registry tickers omit suffixes.
    display = "BTCUSD" if canonical == "BTCUSD" else yahoo
    return MonitoredTicker(display, yahoo, security)


def merge_universe(file_tickers, environment, securities):
    explicit = [*file_tickers, *environment.split()]
    merged = {}
    # User-configured GOOG wins over registry GOOGL, without sharing their prices.
    for symbol in sorted([row["provider_symbol"] for row in securities]) + sorted(explicit):
        item = resolve(symbol, securities)
        previous = merged.get(item.identity)
        if previous is None or item.ticker == "GOOG" or previous.ticker != "GOOG":
            merged[item.identity] = item
    return sorted(merged.values(), key=lambda item: item.ticker)


def save_tickers(path, universe):
    path = Path(path)
    content = "".join(f"{item.ticker}\n" for item in universe)
    if path.exists() and path.read_text() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(content)
    temporary.replace(path)
    return True


def synchronize(path, environment, securities, override=None):
    universe = merge_universe(read_tickers(path), environment, securities)
    save_tickers(path, universe)
    return [resolve(override, securities)] if override else universe
