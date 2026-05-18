from __future__ import annotations

import unittest

from polymarket_python.models import AppState, Candle, CandleColor, SignalDirection
from polymarket_python.strategy import evaluate_signal, find_trigger_candle


def candle(start_ms: int, open_: float, close: float) -> Candle:
    c = Candle(
        open=open_,
        close=close,
        high=max(open_, close) + 1,
        low=min(open_, close) - 1,
        volume=10,
        open_time_ms=start_ms,
    )
    c.color = CandleColor.GREEN if close > open_ else CandleColor.RED if close < open_ else CandleColor.DOJI
    return c


class StrategyTests(unittest.TestCase):
    def test_trigger_is_third_closed_candle_before_final_cutoff(self) -> None:
        start = 1_779_085_200_000
        state = AppState()
        state.window.window_start_ms = start
        state.window.ptb = 100
        state.window.ptb_binance = 100
        state.poly_up_odds = 0.45
        state.poly_down_odds = 0.55
        state.indicators.valid = True
        state.indicators.atr = 20
        state.indicators.vol_sma = 10
        state.klines = [
            candle(start, 100, 102),
            candle(start + 60_000, 102, 104),
            candle(start + 120_000, 104, 108),
        ]

        trigger = find_trigger_candle(state)
        signal, rejection = evaluate_signal(state, start + 180_000)

        self.assertEqual(trigger.open_time_ms, start + 120_000)
        self.assertIsNone(rejection)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.UP)


if __name__ == "__main__":
    unittest.main()
