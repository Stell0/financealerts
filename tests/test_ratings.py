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


def supporting_assessment(direction, score):
    raw = score if direction == "Buy" else 10 - score
    return assessment(
        **{
            **dict.fromkeys(FUNDAMENTALS, str(raw * 10)),
            "risk_penalty": str((10 - raw) * 10),
        }
    )


class RatingTests(unittest.TestCase):
    def test_near_rsi_bands_and_inclusive_unrounded_support_cutoff(self):
        for direction, values in (
            ("Buy", (30.000001, 32, 34.999999)),
            ("Sell", (65.000001, 68, 69.999999)),
        ):
            for support in (0, 6.999999, 7.0, 7.000001, 10):
                with patch(
                    "ratings.technical_scores",
                    return_value=dict.fromkeys(
                        ["bollinger", "macd", "moving_averages"], support
                    ),
                ):
                    for rsi in values:
                        with self.subTest(
                            direction=direction, rsi=rsi, support=support
                        ):
                            candidate, _ = rate(
                                frame(rsi),
                                supporting_assessment(direction, support),
                                NOW,
                            )
                            self.assertEqual(
                                candidate, direction if support >= 7 else None
                            )

    def test_outer_rsi_boundaries_are_strict_even_with_maximum_support(self):
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 10),
        ):
            for direction in ("Buy", "Sell"):
                for rsi in (35, 35.000001, 50, 64.999999, 65):
                    with self.subTest(direction=direction, rsi=rsi):
                        self.assertIsNone(
                            rate(frame(rsi), supporting_assessment(direction, 10), NOW)[
                                0
                            ]
                        )

    def test_extreme_rsi_is_unconditional_including_exact_thresholds(self):
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 0),
        ):
            for direction, values in (("Buy", (0, 20, 30)), ("Sell", (70, 80, 100))):
                for research in (
                    supporting_assessment(direction, 0),
                    assessment(expires_at="2026-10-17T00:00:00Z"),
                    None,
                    assessment(expires_at="invalid"),
                ):
                    for rsi in values:
                        with self.subTest(
                            direction=direction, rsi=rsi, research=research
                        ):
                            self.assertEqual(
                                rate(frame(rsi), research, NOW)[0], direction
                            )

    def test_non_rsi_support_normalizes_weights_and_preserves_star_scores(self):
        for direction, rsi in (("Buy", 32), ("Sell", 68)):
            with (
                self.subTest(direction=direction),
                patch(
                    "ratings.technical_scores",
                    return_value=dict.fromkeys(
                        ["bollinger", "macd", "moving_averages"], 9
                    ),
                ),
            ):
                # 9 * 25% + 6 * 50% = 5.25, normalized by 75% = exactly 7.
                candidate, scores = rate(
                    frame(rsi), supporting_assessment(direction, 6), NOW
                )
                self.assertEqual(candidate, direction)
                self.assertEqual(scores[direction], 6.2)
                # Opposing fundamentals must not qualify this direction.
                opposite = "Sell" if direction == "Buy" else "Buy"
                self.assertIsNone(
                    rate(frame(rsi), supporting_assessment(opposite, 6), NOW)[0]
                )
                for research in (
                    assessment(expires_at="2026-10-17T00:00:00Z"),
                    None,
                    assessment(expires_at="invalid"),
                ):
                    self.assertIsNone(rate(frame(rsi), research, NOW)[0])

    def test_actual_bullish_and_bearish_subscores_qualify_the_correct_direction(self):
        bullish = frame(32)
        bullish["Close"] = 91
        bearish = frame(68)
        bearish["Close"] = 109
        bearish["MACD"] = -2
        bearish["MACD_SIGNAL"] = -1
        bearish["MACD_HIST"] = [1, -0.5]
        bearish["SMA200"] = 110
        for direction, data in (("Buy", bullish), ("Sell", bearish)):
            with self.subTest(direction=direction):
                self.assertEqual(
                    rate(data, supporting_assessment(direction, 9), NOW)[0], direction
                )
                opposite = "Sell" if direction == "Buy" else "Buy"
                self.assertIsNone(
                    rate(data, supporting_assessment(opposite, 9), NOW)[0]
                )

    def test_rsi_inclusive_thresholds_and_scaling(self):
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 5.0),
        ):
            for rsi, direction, expected in [
                (22, "Buy", 6.0),
                (26, "Buy", 5.5),
                (30, "Buy", 5.0),
                (70, "Sell", 5.0),
                (74, "Sell", 5.5),
                (78, "Sell", 6.0),
            ]:
                actual, scores = rate(frame(rsi), now=NOW)
                self.assertEqual(actual, direction)
                self.assertEqual(scores[direction], expected)
            for rsi in (30.001, 50, 69.999):
                self.assertIsNone(rate(frame(rsi), now=NOW)[0])

    def test_weights_boundaries_and_independence(self):
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1)
        self.assertEqual(WEIGHTS["rsi"], 0.25)
        self.assertAlmostEqual(
            sum(WEIGHTS[key] for key in ("bollinger", "macd", "moving_averages")),
            0.25,
        )
        self.assertAlmostEqual(sum(WEIGHTS[key] for key in FUNDAMENTALS), 0.50)
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

    def test_fundamentals_drive_stars_while_rsi_selects_alerts(self):
        buy_support = assessment(**dict.fromkeys(FUNDAMENTALS, "100"))
        buy_support["risk_penalty"] = "0"
        sell_support = assessment(**dict.fromkeys(FUNDAMENTALS, "0"))
        sell_support["risk_penalty"] = "100"
        with patch(
            "ratings.technical_scores",
            return_value=dict.fromkeys(["bollinger", "macd", "moving_averages"], 5.0),
        ):
            for direction, threshold, extreme, strong, weak in (
                ("Buy", 30, 22, buy_support, sell_support),
                ("Sell", 70, 78, sell_support, buy_support),
            ):
                with self.subTest(direction=direction):
                    candidate, strong_scores = rate(frame(threshold), strong, NOW)
                    weak_candidate, weak_scores = rate(frame(threshold), weak, NOW)
                    self.assertEqual(candidate, direction)
                    self.assertEqual(weak_candidate, direction)
                    self.assertEqual(strong_scores[direction], 7.5)
                    self.assertEqual(weak_scores[direction], 2.5)
                    self.assertEqual(stars(strong_scores[direction]), "⭐⭐⭐⭐")
                    self.assertEqual(stars(weak_scores[direction]), "⭐⭐")
                    self.assertEqual(
                        rate(frame(extreme), strong, NOW)[1][direction], 8.5
                    )
                    self.assertIsNone(rate(frame(50), strong, NOW)[0])

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
            for rsi, direction in ((22, "Buy"), (78, "Sell")):
                candidate, scores = rate(frame(rsi), expired, NOW)
                self.assertEqual(candidate, direction)
                self.assertEqual(scores[direction], 3.5)
                neutral = rate(frame(rsi), None, NOW)[1]
                self.assertEqual(neutral[direction] - scores[direction], 2.5)
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
                self.assertEqual(scores[direction], 5.0)
                self.assertTrue(all(0 <= value <= 5 for value in scores.values()))
                self.assertEqual(stars(scores[direction]), "⭐⭐⭐")

    def test_pls_last_alert_drops_to_two_stars(self):
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
        self.assertEqual(scores["Buy"], 3.7)
        self.assertEqual(stars(scores["Buy"]), "⭐⭐")
        self.assertEqual(rate(data, None, NOW)[1]["Buy"], 6.2)

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
        self.assertEqual(scores["Buy"], 6.2)

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
