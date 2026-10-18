"""Default rating weights and RSI triggers; one source of truth."""

import os

WEIGHTS = {
    # RSI selects notifications; stars balance technicals with fundamentals.
    "rsi": 0.25,
    "bollinger": 0.10,
    "macd": 0.09,
    "moving_averages": 0.06,
    "valuation_score": 0.20,
    "business_quality_score": 0.10,
    "thesis_score": 0.07,
    "balance_sheet_score": 0.05,
    "risk_penalty": 0.08,
}

# Directional favorability for every expired fundamental component, including risk.
EXPIRED_FUNDAMENTAL_SCORE = 0.0


def thresholds():
    lower = float(os.environ.get("RSI_lower", "30"))
    upper = float(os.environ.get("RSI_upper", "70"))
    if not 0 <= lower < upper <= 100:
        raise ValueError("Require 0 <= RSI_lower < RSI_upper <= 100")
    return lower, upper
