"""Daily independent market scan enriched only with PaperTrader fundamentals."""

import logging
import os
import sys
from datetime import datetime, timezone

import indicators
import telegram_alert
import yahoo_finance_api
from papertrader_data import load_snapshot
from ratings import rate, read_assessments, stars
from registry import synchronize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def scan(universe, assessments, now=None, cache_dir="data"):
    now = now or datetime.now(timezone.utc)
    candidates, failures = [], []
    for item in universe:
        try:
            security = item.security or {}
            prices = yahoo_finance_api.retrieve_daily_prices(
                item.yahoo_symbol,
                period=550,
                now=now,
                venue_mic=security.get("venue_mic"),
                cache_dir=cache_dir,
            )
            frame = indicators.calculate(prices)
            direction, scores = rate(
                frame, assessments.get(security.get("security_id")), now
            )
            if direction:
                candidates.append(
                    {
                        "item": item,
                        "direction": direction,
                        "score": scores[direction],
                        "bar": prices.iloc[-1],
                        "date": prices.index[-1].date(),
                    }
                )
        except Exception:
            logging.exception("Error processing ticker %s", item.ticker)
            failures.append(item.ticker)
    return candidates, failures


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    securities, text = load_snapshot()
    universe = synchronize(
        "config/tickers.txt",
        os.environ.get("TICKER_LIST", ""),
        securities,
        argv[0] if argv else None,
    )
    candidates, failures = scan(universe, read_assessments(text))
    # M3 replaces this compact interim report with linked HTML and delivery state.
    lines = []
    for direction in ("Buy", "Sell"):
        selected = sorted(
            (row for row in candidates if row["direction"] == direction),
            key=lambda row: (-row["score"], row["item"].ticker),
        )
        if selected:
            lines.append(direction + ":")
            lines.extend(
                f"{row['item'].ticker} | {stars(row['score'])}" for row in selected
            )
    if lines:
        telegram_alert.send_alert("\n".join(lines))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
