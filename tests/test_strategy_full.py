"""Test: can Strategy B actually trigger a trade?"""
from __future__ import annotations

import unittest
from polymarket_python.models import AppState, Candle, CandleColor, SignalDirection
from polymarket_python.strategy import evaluate_signal, find_trigger_candle, detect_trend
from polymarket_python.state import capture_ptb_from_binance, record_first_in_window
from polymarket_python.indicators import update_indicators
from polymarket_python.scheduler import calculate_window_start


def make_candle(start_ms: int, open_: float, close: float, high: float | None = None, low: float | None = None) -> Candle:
    h = high if high is not None else max(open_, close) + 2
    l = low if low is not None else min(open_, close) - 2
    c = Candle(open=open_, close=close, high=h, low=l, volume=10, open_time_ms=start_ms)
    c.color = CandleColor.GREEN if close > open_ else CandleColor.RED if close < open_ else CandleColor.DOJI
    return c


def seed_history(state: AppState, window_start: int) -> None:
    """Add 6 historical candles before the window for valid indicators (ATR needs period+1 candles = 6)."""
    for i in range(6):
        offset = window_start - (6 - i) * 60_000
        state.klines.append(make_candle(offset, 99_500 + i * 50, 99_550 + i * 50))


class TestStrategySignals(unittest.TestCase):
    """Test Strategy B signal triggering — no real money."""

    def test_bullish_breakout_triggers_up_signal(self) -> None:
        """Full scenario: BTC breaks above PTB with bullish trend → fires UP signal."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        update_indicators(state)
        self.assertTrue(state.indicators.valid, "Indicators must be valid")

        # 3 bullish candles inside window
        c1 = make_candle(window_start, 100_000, 100_200)
        c2 = make_candle(window_start + 60_000, 100_200, 100_500)
        c3 = make_candle(window_start + 120_000, 100_500, 100_900)
        state.klines.extend([c1, c2, c3])
        record_first_in_window(state, c1)

        # Trigger: 4th candle, bullish, breaks above PTB (close=101_200 > PTB=100_000)
        trigger = make_candle(window_start + 180_000, 100_900, 101_200)
        state.klines.append(trigger)

        signal, rejection = evaluate_signal(state, window_start + 120_000)

        self.assertIsNotNone(signal, f"Expected UP signal, got rejection: {rejection}")
        self.assertEqual(signal.direction, SignalDirection.UP)

    def test_bearish_breakout_triggers_down_signal(self) -> None:
        """Full scenario: BTC drops below PTB with bearish trend → fires DOWN signal."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        update_indicators(state)

        # 3 bearish candles inside window
        c1 = make_candle(window_start, 100_000, 99_800)
        c2 = make_candle(window_start + 60_000, 99_800, 99_500)
        c3 = make_candle(window_start + 120_000, 99_500, 99_100)
        state.klines.extend([c1, c2, c3])
        record_first_in_window(state, c1)

        # Trigger: 4th candle, bearish, breaks below PTB (close=98_800 < PTB=100_000)
        trigger = make_candle(window_start + 180_000, 99_100, 98_800)
        state.klines.append(trigger)

        signal, rejection = evaluate_signal(state, window_start + 120_000)

        self.assertIsNotNone(signal, f"Expected DOWN signal, got rejection: {rejection}")
        self.assertEqual(signal.direction, SignalDirection.DOWN)

    def test_rejects_too_early(self) -> None:
        """Check before 60s guard → TooEarly."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        c1 = make_candle(window_start, 100_000, 100_200)
        c2 = make_candle(window_start + 60_000, 100_200, 100_500)
        c3 = make_candle(window_start + 120_000, 100_500, 100_900)
        trigger = make_candle(window_start + 180_000, 100_900, 101_200)
        state.klines.extend([c1, c2, c3, trigger])
        update_indicators(state)
        record_first_in_window(state, c1)

        _, rejection = evaluate_signal(state, window_start + 30_000)
        self.assertEqual(rejection.reason, "TooEarly")

    def test_rejects_ptb_not_ready(self) -> None:
        """No PTB captured → PtbNotReady."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        # NO ptb capture

        seed_history(state, window_start)
        c1 = make_candle(window_start, 100_000, 99_800)
        c2 = make_candle(window_start + 60_000, 99_800, 99_500)
        c3 = make_candle(window_start + 120_000, 99_500, 99_100)
        trigger = make_candle(window_start + 180_000, 99_100, 98_800)
        state.klines.extend([c1, c2, c3, trigger])
        update_indicators(state)
        record_first_in_window(state, c1)

        _, rejection = evaluate_signal(state, window_start + 120_000)
        self.assertEqual(rejection.reason, "PtbNotReady")

    def test_rejects_trend_flat(self) -> None:
        """Flat candles → TrendFlat."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        update_indicators(state)
        self.assertTrue(state.indicators.valid)

        # 3 flat (doji) candles inside window — last_close == 3rd-back open → Flat
        f1 = make_candle(window_start, 100_000, 100_000)
        f2 = make_candle(window_start + 60_000, 100_000, 100_000)
        f3 = make_candle(window_start + 120_000, 100_000, 100_000)
        ftrigger = make_candle(window_start + 180_000, 100_000, 100_000)
        state.klines.extend([f1, f2, f3, ftrigger])
        record_first_in_window(state, f1)

        _, rejection = evaluate_signal(state, window_start + 120_000)
        self.assertEqual(rejection.reason, "TrendFlat")

    def test_rejects_color_mismatch_bullish_trigger_red(self) -> None:
        """Bullish trend but trigger is red → ColorMismatch."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        update_indicators(state)

        # 3 bullish candles → trend = Bullish
        c1 = make_candle(window_start, 100_000, 100_200)
        c2 = make_candle(window_start + 60_000, 100_200, 100_500)
        c3 = make_candle(window_start + 120_000, 100_500, 100_900)
        state.klines.extend([c1, c2, c3])
        record_first_in_window(state, c1)

        # Trigger: red (close < open), doesn't match bullish trend → ColorMismatch
        trigger = make_candle(window_start + 180_000, 100_900, 99_800)
        state.klines.append(trigger)

        _, rejection = evaluate_signal(state, window_start + 205_000)
        self.assertIsNotNone(rejection, "Expected ColorMismatch")
        self.assertEqual(rejection.reason, "ColorMismatch")

    def test_rejects_color_mismatch_bearish_trigger_green(self) -> None:
        """Bearish trend but trigger is green → ColorMismatch."""
        window_start = calculate_window_start(int(1_779_085_200_000))

        state = AppState()
        state.window.window_start_ms = window_start
        capture_ptb_from_binance(state, 100_000.0, window_start + 1_000)

        seed_history(state, window_start)
        update_indicators(state)

        # 3 bearish candles → trend = Bearish
        c1 = make_candle(window_start, 100_000, 99_800)
        c2 = make_candle(window_start + 60_000, 99_800, 99_500)
        c3 = make_candle(window_start + 120_000, 99_500, 99_100)
        state.klines.extend([c1, c2, c3])
        record_first_in_window(state, c1)

        # Trigger: green (close > open), doesn't match bearish trend → ColorMismatch
        trigger = make_candle(window_start + 180_000, 99_100, 101_200)
        state.klines.append(trigger)

        _, rejection = evaluate_signal(state, window_start + 205_000)
        self.assertIsNotNone(rejection, "Expected ColorMismatch")
        self.assertEqual(rejection.reason, "ColorMismatch")



if __name__ == "__main__":
    unittest.main()