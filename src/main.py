"""Daily independent market scan enriched only with PaperTrader fundamentals."""

import logging
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone

import yfinance as yf

import indicators
import yahoo_finance_api
from notifications import YAHOO_EXCHANGES, deliver
from papertrader_data import load_snapshot
from ratings import rate, read_assessments, research_status
from registry import read_short_watchlist, save_securities, synchronize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def scan(universe, assessments, now=None, cache_dir="data"):
    now = now or datetime.now(timezone.utc)
    candidates, failures = [], []
    processed, skipped = 0, 0
    for item in universe:
        if item.universe == "research_only":
            logging.info("Skipping research-only security %s", item.ticker)
            continue
        if (item.security or {}).get("status") == "acquired":
            logging.info("Skipping acquired security %s", item.ticker)
            skipped += 1
            continue
        processed += 1
        try:
            if item.security is None and item.yahoo_symbol != "BTC-USD":
                info = yf.Ticker(item.yahoo_symbol).get_info()
                venue = YAHOO_EXCHANGES.get(info.get("exchange"))
                if (
                    info.get("symbol") != item.yahoo_symbol
                    or not venue
                    or not info.get("longName")
                ):
                    raise ValueError(
                        "Unverified company/venue metadata; retry after registry import"
                    )
                item = replace(
                    item,
                    security={"company_name": info["longName"], "venue_mic": venue},
                )
            if item.yahoo_symbol == "BTC-USD" and item.security is None:
                item = replace(
                    item, security={"company_name": "Bitcoin", "venue_mic": "XOFF"}
                )
            security = item.security or {}
            prices = yahoo_finance_api.retrieve_daily_prices(
                item.yahoo_symbol,
                period=550,
                now=now,
                venue_mic=security.get("venue_mic"),
                cache_dir=cache_dir,
            )
            frame = indicators.calculate(prices)
            assessment = assessments.get(security.get("security_id"))
            direction, scores = rate(frame, assessment, now, universe=item.universe)
            if direction:
                candidates.append(
                    {
                        "item": item,
                        "direction": direction,
                        "score": scores[direction],
                        "rsi": float(frame.iloc[-1]["RSI"]),
                        "research_status": research_status(assessment, now),
                        "bar": prices.iloc[-1],
                        "date": prices.index[-1].date(),
                    }
                )
        except Exception:
            logging.exception("Error processing ticker %s", item.ticker)
            failures.append(item.ticker)
    logging.info(
        "Scan complete: %d processed, %d acquired skipped, %d candidates, %d failed; failed tickers: %s",
        processed, skipped, len(candidates), len(failures), ", ".join(failures) or "none",
    )
    return candidates, failures


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    securities, text = load_snapshot()
    universe = synchronize(
        "config/tickers.txt",
        os.environ.get("TICKER_LIST", ""),
        securities,
        argv[0] if argv else None,
        short_watchlist=read_short_watchlist("config/short_watchlist.csv"),
    )
    save_securities("config/securities.csv", securities)
    migration = yahoo_finance_api.migrate_caches(securities=securities)
    candidates, failures = scan(universe, read_assessments(text))
    try:
        deliver(candidates)
    except Exception:
        logging.exception(
            "Telegram delivery failed; undelivered alerts remain eligible for retry"
        )
        return 1
    return 1 if failures or migration["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
