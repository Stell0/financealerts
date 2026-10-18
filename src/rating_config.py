"""Default rating weights and RSI triggers; one source of truth."""

import os

WEIGHTS = {
    "rsi": 0.50,
    "bollinger": 0.08,
    "macd": 0.07,
    "moving_averages": 0.05,
    "valuation_score": 0.12,
    "business_quality_score": 0.06,
    "thesis_score": 0.04,
    "balance_sheet_score": 0.03,
    "risk_penalty": 0.05,
}


def thresholds():
    lower = float(os.environ.get("RSI_lower", "30"))
    upper = float(os.environ.get("RSI_upper", "70"))
    if not 0 <= lower < upper <= 100:
        raise ValueError("Require 0 <= RSI_lower < RSI_upper <= 100")
    return lower, upper
