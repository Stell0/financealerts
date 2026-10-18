import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd
import talib

import indicators
from rating_config import WEIGHTS, thresholds
from ratings import FUNDAMENTALS, fundamental_scores, rate, read_assessments, stars

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def frame(rsi):
    return pd.DataFrame(
        {
            "Close": [95.0, 96.0],
            "RSI": [rsi, rsi],
            "BB_UPPER": [110.0, 110.0],
            "BB_LOWER": [90.0, 90.0],
            "MACD": [-2.0, -1.0],
            "MACD_SIGNAL": [-1.0, -1.5],
            "MACD_HIST": [-1.0, 0.5],
            "SMA50": [100.0, 100.0],
            "SMA200": [90.0, 90.0],
        }
    )


def assessment(**changes):
    return {
        **dict.fromkeys(FUNDAMENTALS, "80"),
        "assessed_at": "2026-10-01T00:00:00Z",
        "expires_at": "2026-11-01T00:00:00Z",
        **changes,
    }


class RatingTests(unittest.TestCase):
    def test_rsi_inclusive_thresholds_and_scaling(self):
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 5.0),
        ):
            for rsi, direction, expected in [
                (20, "Buy", 7.5),
                (25, "Buy", 6.2),
                (30, "Buy", 5.0),
                (70, "Sell", 5.0),
                (75, "Sell", 6.2),
                (80, "Sell", 7.5),
            ]:
                actual, scores = rate(frame(rsi), now=NOW)
                self.assertEqual(actual, direction)
                self.assertEqual(scores[direction], expected)
            for rsi in (30.001, 50, 69.999):
                self.assertIsNone(rate(frame(rsi), now=NOW)[0])

    def test_weights_boundaries_and_independence(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1)
        self.assertEqual(WEIGHTS["rsi"], 0.5)
        for rsi in (0, 20, 30, 50, 70, 80, 100):
            _, scores = rate(frame(rsi), assessment(), NOW)
            self.assertTrue(all(0 <= value <= 10 for value in scores.values()))
        _, scores = rate(frame(30), assessment(), NOW)
        self.assertNotEqual(scores["Sell"], 10 - scores["Buy"])
        base = rate(frame(20), assessment(timing_score="0"), NOW)
        self.assertEqual(base, rate(frame(20), assessment(timing_score="100"), NOW))
        low_risk = rate(frame(20), assessment(risk_penalty="0"), NOW)[1]
        high_risk = rate(frame(20), assessment(risk_penalty="100"), NOW)[1]
        self.assertGreater(low_risk["Buy"], high_risk["Buy"])
        self.assertLess(low_risk["Sell"], high_risk["Sell"])

    def test_neutral_invalid_missing_and_partial_components(self):
        neutral = dict.fromkeys(FUNDAMENTALS, 5.0)
        for invalid in (
            None,
            assessment(assessed_at="2026-11-01T00:00:00Z"),
            assessment(expires_at="invalid"),
            assessment(expires_at=None),
            assessment(expires_at="2026-11-01"),
        ):
            self.assertEqual(fundamental_scores(invalid, NOW), neutral)
            self.assertEqual(rate(frame(20), invalid, NOW)[0], "Buy")
        scores = fundamental_scores(
            assessment(valuation_score="nan", thesis_score="101"), NOW
        )
        self.assertEqual(scores["valuation_score"], 5.0)
        self.assertEqual(scores["thesis_score"], 5.0)
        self.assertEqual(scores["business_quality_score"], 8.0)
        self.assertEqual(read_assessments("wrong\nheader\n"), {})
        with self.assertRaises(ValueError):
            rate(frame(float("nan")), now=NOW)

    def test_expired_assessments_penalize_both_directions_without_changing_triggers(
        self,
    ):
        expired = assessment(expires_at="2026-10-18T00:00:00Z")
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 5.0),
        ):
            for rsi, direction in ((20, "Buy"), (80, "Sell")):
                candidate, scores = rate(frame(rsi), expired, NOW)
                self.assertEqual(candidate, direction)
                self.assertEqual(scores[direction], 6.0)
                neutral = rate(frame(rsi), None, NOW)[1]
                for side in ("Buy", "Sell"):
                    self.assertAlmostEqual(neutral[side] - scores[side], 1.5)
            self.assertIsNone(rate(frame(50), expired, NOW)[0])

    def test_expiry_boundary_and_timezone(self):
        for timestamp in (
            "2026-10-17T23:59:59Z",
            "2026-10-18T00:00:00Z",
            "2026-10-18T02:00:00+02:00",
        ):
            self.assertIsNone(fundamental_scores(assessment(expires_at=timestamp), NOW))
        fresh = assessment(expires_at="2026-10-18T00:00:01Z")
        self.assertEqual(fundamental_scores(fresh, NOW)["valuation_score"], 8.0)

    def test_expired_fundamentals_cannot_become_a_sell_reward(self):
        expired = assessment(expires_at="2026-10-17T00:00:00Z")
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 10.0),
        ):
            for rsi, direction in ((0, "Buy"), (100, "Sell")):
                scores = rate(frame(rsi), expired, NOW)[1]
                self.assertEqual(scores[direction], 7.0)
                self.assertTrue(all(0 <= value <= 7 for value in scores.values()))

    def test_pls_last_alert_drops_to_three_stars(self):
        data = frame(22.6594959723)
        data["Close"] = 2.980000019
        data["BB_UPPER"] = 4.3928122107
        data["BB_LOWER"] = 2.9391877826
        data["MACD"] = -0.3691902662
        data["MACD_SIGNAL"] = -0.3136730841
        data["MACD_HIST"] = [-0.06, -0.0555171821]
        data["SMA50"] = 4.3915101957
        data["SMA200"] = 4.9247889006
        expired = assessment(
            assessed_at="2026-08-31T21:53:45Z", expires_at="2026-09-30T21:53:45Z"
        )
        direction, scores = rate(data, expired, NOW)
        self.assertEqual(direction, "Buy")
        self.assertEqual(scores["Buy"], 5.5)
        self.assertEqual(stars(scores["Buy"]), "⭐⭐⭐")
        self.assertEqual(rate(data, None, NOW)[1]["Buy"], 7.0)

    def test_missing_warmups_are_neutral_without_veto(self):
        data = frame(20)
        data[
            [
                "SMA50",
                "SMA200",
                "MACD",
                "MACD_SIGNAL",
                "MACD_HIST",
                "BB_UPPER",
                "BB_LOWER",
            ]
        ] = np.nan
        direction, scores = rate(data, now=NOW)
        self.assertEqual(direction, "Buy")
        self.assertEqual(scores["Buy"], 7.5)

    def test_threshold_configuration_and_stars(self):
        with patch.dict("os.environ", {"RSI_lower": "25", "RSI_upper": "75"}):
            self.assertIsNone(rate(frame(30), now=NOW)[0])
            self.assertEqual(rate(frame(25), now=NOW)[0], "Buy")
        with patch.dict("os.environ", {"RSI_lower": "80", "RSI_upper": "70"}):
            with self.assertRaises(ValueError):
                thresholds()
        for value, count in [
            (0, 1),
            (2, 1),
            (2.1, 2),
            (4, 2),
            (4.1, 3),
            (6, 3),
            (6.1, 4),
            (8, 4),
            (8.1, 5),
            (10, 5),
        ]:
            self.assertEqual(stars(value), "⭐" * count)

    def test_indicators_match_standard_talib_definitions(self):
        close = np.arange(260, dtype=float) + 100 + np.sin(np.arange(260)) * 10
        result = indicators.calculate(pd.DataFrame({"Close": close}))
        for column, expected in [
            ("SMA50", talib.SMA(close, 50)),
            ("SMA200", talib.SMA(close, 200)),
            ("RSI", talib.RSI(close, 14)),
        ]:
            np.testing.assert_allclose(result[column], expected, equal_nan=True)
        self.assertNotAlmostEqual(result.iloc[-1]["SMA50"], talib.SMA(close, 40)[-1])
        macd, signal, hist = talib.MACD(close, 12, 26, 9)
        for column, values in [
            ("MACD", macd),
            ("MACD_SIGNAL", signal),
            ("MACD_HIST", hist),
        ]:
            np.testing.assert_allclose(result[column], values, equal_nan=True)
        upper, middle, lower = talib.BBANDS(close, 20, 2, 2)
        for column, values in [
            ("BB_UPPER", upper),
            ("BB_MIDDLE", middle),
            ("BB_LOWER", lower),
        ]:
            np.testing.assert_allclose(result[column], values, equal_nan=True)
