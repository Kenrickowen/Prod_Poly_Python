from __future__ import annotations

import unittest

from polymarket_python.models import AppState, Candle, CandleColor, SignalDirection
from polymarket_python.state import capture_ptb_from_binance, get_signal_ptb
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
    def test_trigger_is_fourth_closed_candle_before_final_cutoff(self) -> None:
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
        # 4 candles: c1,c2,c3 are trend candles; c4 is the trigger (4th candle)
        c1 = candle(start, 100, 102)
        c2 = candle(start + 60_000, 102, 104)
        c3 = candle(start + 120_000, 104, 108)
        trigger = candle(start + 180_000, 108, 110)  # 4th candle = trigger
        state.klines = [c1, c2, c3, trigger]

        found = find_trigger_candle(state)
        self.assertEqual(found.open_time_ms, start + 180_000)
        signal, rejection = evaluate_signal(state, start + 180_000)
        self.assertIsNone(rejection)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.direction, SignalDirection.UP)

    def test_signal_ptb_stays_fixed_after_ticker_updates(self) -> None:
        state = AppState()
        start = 1_779_085_200_000
        capture_ptb_from_binance(state, 100.0, start)
        capture_ptb_from_binance(state, 105.0, start + 30_000)

        self.assertEqual(state.window.ptb, 100.0)
        self.assertEqual(state.window.ptb_binance, 105.0)
        self.assertEqual(get_signal_ptb(state), 100.0)


if __name__ == "__main__":
    unittest.main()
