"""Independent ratings and RSI eligibility with directional non-RSI support."""

import csv
import logging
import math
from datetime import datetime, timezone
from io import StringIO

from rating_config import (
    EXPIRED_FUNDAMENTAL_SCORE,
    NON_RSI_SUPPORT_MIN,
    RSI_SUPPORT_BAND,
    WEIGHTS,
    thresholds,
)

FUNDAMENTALS = (
    "valuation_score",
    "business_quality_score",
    "thesis_score",
    "balance_sheet_score",
    "risk_penalty",
)


def clamp(value):
    return max(0.0, min(10.0, value))


def finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def read_assessments(text):
    if not text:
        return {}
    reader = csv.DictReader(StringIO(text.lstrip("\ufeff")))
    fields = reader.fieldnames or []
    expiry_field = "expires_at" if "expires_at" in fields else "valid_until"
    if len(fields) != len(set(fields)) or not {
        "security_id",
        "assessed_at",
        expiry_field,
    }.issubset(fields):
        logging.warning(
            "PaperTrader assessments lack required fields; using neutral fundamentals"
        )
        return {}
    missing = sorted(set(FUNDAMENTALS) - set(fields))
    if missing:
        logging.warning(
            "PaperTrader assessments lack scoring fields: %s; unavailable components remain neutral",
            ", ".join(missing),
        )
    output = {}
    for row in reader:
        sid = row.get("security_id")
        if not sid or None in row:
            logging.warning("Invalid PaperTrader assessment row")
            continue
        if sid in output:
            logging.warning(
                "Duplicate PaperTrader assessment: %s; using neutral fundamentals", sid
            )
            output[sid] = None
        else:
            row["expires_at"] = row[expiry_field]
            output[sid] = row
    return output


def fundamental_scores(assessment, now=None):
    """Return raw 0–10 components, or None for a structurally valid expired assessment."""
    now = now or datetime.now(timezone.utc)
    neutral = dict.fromkeys(FUNDAMENTALS, 5.0)
    if not assessment:
        logging.warning("Missing PaperTrader assessment; using neutral fundamentals")
        return neutral
    try:
        assessed = datetime.fromisoformat(
            str(assessment.get("assessed_at")).replace("Z", "+00:00")
        )
        expires = datetime.fromisoformat(
            str(assessment.get("expires_at")).replace("Z", "+00:00")
        )
        if (
            assessed.tzinfo is None
            or expires.tzinfo is None
            or assessed > now
            or expires <= assessed
        ):
            raise ValueError("invalid assessment validity interval")
    except (KeyError, ValueError, TypeError) as error:
        logging.warning(
            "Invalid PaperTrader assessment: %s; using neutral fundamentals",
            error,
        )
        return neutral
    if now >= expires:
        logging.warning(
            "Expired PaperTrader assessment for %s; penalizing both Buy and Sell fundamentals",
            assessment.get("security_id", "unknown security"),
        )
        return None
    for field in FUNDAMENTALS:
        value = finite(assessment.get(field))
        if value is None or not 0 <= value <= 100:
            logging.warning("Unavailable PaperTrader %s; using neutral value", field)
        else:
            neutral[field] = value / 10.0
    return neutral


def sign(value):
    return (value > 0) - (value < 0)


def technical_scores(frame, direction):
    row = frame.iloc[-1]
    close = float(row["Close"])
    polarity = 1 if direction == "Buy" else -1
    scores = dict.fromkeys(("bollinger", "macd", "moving_averages"), 5.0)
    upper, lower = finite(row.get("BB_UPPER")), finite(row.get("BB_LOWER"))
    if upper is not None and lower is not None and upper > lower:
        scores["bollinger"] = clamp(
            10
            * ((upper - close) if direction == "Buy" else (close - lower))
            / (upper - lower)
        )
    line, signal = finite(row.get("MACD")), finite(row.get("MACD_SIGNAL"))
    hist = finite(row.get("MACD_HIST"))
    previous = finite(frame.iloc[-2].get("MACD_HIST")) if len(frame) > 1 else None
    if None not in (line, signal, hist, previous):
        scores["macd"] = clamp(
            5 + polarity * (2 * sign(line - signal) + 3 * sign(hist - previous))
        )
    short, long = finite(row.get("SMA50")), finite(row.get("SMA200"))
    if short is not None and long is not None:
        scores["moving_averages"] = clamp(
            5 + polarity * (2.5 * sign(short - long) + 2.5 * sign(close - short))
        )
    return scores


def rate(frame, assessment=None, now=None, lower=None, upper=None):
    default_lower, default_upper = thresholds()
    lower = default_lower if lower is None else lower
    upper = default_upper if upper is None else upper
    if frame.empty or finite(frame.iloc[-1].get("RSI")) is None:
        raise ValueError("Insufficient valid history for RSI(14)")
    rsi = float(frame.iloc[-1]["RSI"])
    fundamental = fundamental_scores(assessment, now)
    output = {}
    support = {}
    support_weight = math.fsum(
        weight for field, weight in WEIGHTS.items() if field != "rsi"
    )
    for direction in ("Buy", "Sell"):
        components = technical_scores(frame, direction)
        components["rsi"] = clamp(
            5 + ((lower - rsi) if direction == "Buy" else (rsi - upper)) / 2
        )
        if fundamental is None:
            # Apply expiry after choosing direction: mirroring zero raw values would
            # incorrectly reward Sell alerts instead of penalizing stale research.
            components.update(dict.fromkeys(FUNDAMENTALS, EXPIRED_FUNDAMENTAL_SCORE))
        else:
            for field, value in fundamental.items():
                if direction == "Buy":
                    components[field] = 10 - value if field == "risk_penalty" else value
                else:
                    components[field] = value if field == "risk_penalty" else 10 - value
        output[direction] = round(
            clamp(sum(WEIGHTS[field] * value for field, value in components.items())), 1
        )
        # Reuse the same directional subscores, including the expiry penalty.
        # Eligibility uses unrounded support; star rounding must not admit < 7.
        support[direction] = clamp(
            math.fsum(
                WEIGHTS[field] * value
                for field, value in components.items()
                if field != "rsi"
            )
            / support_weight
        )
    if rsi <= lower:
        candidate = "Buy"
    elif rsi >= upper:
        candidate = "Sell"
    elif (
        lower < rsi < lower + RSI_SUPPORT_BAND and support["Buy"] >= NON_RSI_SUPPORT_MIN
    ):
        candidate = "Buy"
    elif (
        upper - RSI_SUPPORT_BAND < rsi < upper
        and support["Sell"] >= NON_RSI_SUPPORT_MIN
    ):
        candidate = "Sell"
    else:
        candidate = None
    return candidate, output


def stars(score):
    return "⭐" * max(1, min(5, math.ceil(clamp(score) / 2)))
