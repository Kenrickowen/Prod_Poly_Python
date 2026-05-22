from __future__ import annotations

import unittest

from polymarket_python.models import AppState, SignalDirection
from polymarket_python.strategy import evaluate_signal
from polymarket_python.strategy_momentum import fair_up_probability


class MomentumStrategyTests(unittest.TestCase):
    def _state(self, price: float, up: float, down: float) -> AppState:
        window_start = 1_779_085_200_000
        state = AppState()
        state.strategy_mode = "momentum"
        state.window.window_start_ms = window_start
        state.window.ptb = 100.0
        state.last_price = price
        state.poly_up_odds = up
        state.poly_down_odds = down
        return state

    def test_fair_probability_moves_with_price_and_time(self) -> None:
        fair_above = fair_up_probability(101.0, 100.0, 0.01, 120_000)
        fair_below = fair_up_probability(99.0, 100.0, 0.01, 120_000)
        fair_late = fair_up_probability(101.0, 100.0, 0.01, 30_000)

        self.assertGreater(fair_above, 0.5)
        self.assertLess(fair_below, 0.5)
        self.assertGreater(fair_late, fair_above)

    def test_bullish_edge_emits_up_paper_signal(self) -> None:
        state = self._state(price=102.0, up=0.50, down=0.50)

        signal, rejection = evaluate_signal(state, state.window.window_start_ms + 90_000)

        self.assertIsNone(rejection)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.UP)
        self.assertTrue(signal.paper_only)
        self.assertGreater(signal.edge, 0.05)

    def test_bearish_edge_emits_down_paper_signal(self) -> None:
        state = self._state(price=98.0, up=0.50, down=0.50)

        signal, rejection = evaluate_signal(state, state.window.window_start_ms + 90_000)

        self.assertIsNone(rejection)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.DOWN)
        self.assertTrue(signal.paper_only)

    def test_weak_edge_rejects(self) -> None:
        state = self._state(price=100.0, up=0.50, down=0.50)

        signal, rejection = evaluate_signal(state, state.window.window_start_ms + 90_000)

        self.assertIsNone(signal)
        self.assertEqual(rejection.reason, "EdgeTooSmall")

    def test_wide_spread_rejects(self) -> None:
        state = self._state(price=102.0, up=0.54, down=0.54)

        signal, rejection = evaluate_signal(state, state.window.window_start_ms + 90_000)

        self.assertIsNone(signal)
        self.assertEqual(rejection.reason, "SpreadTooWide")

    def test_chainlink_divergence_rejects(self) -> None:
        state = self._state(price=102.0, up=0.50, down=0.50)
        state.chainlink_price = 100.0

        signal, rejection = evaluate_signal(state, state.window.window_start_ms + 90_000)

        self.assertIsNone(signal)
        self.assertEqual(rejection.reason, "ChainlinkDivergence")


if __name__ == "__main__":
    unittest.main()
