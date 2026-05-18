"""
Strategy B — 5m BTC Breakout signal evaluation.

Signal fires when ALL conditions are true:
1. Trend: Bullish or Bearish from first 3 candles INSIDE window
2. Trigger: 3rd closed candle inside window confirms trend before final cutoff
3. PTB Side Check: UP → trigger.close > PTB, DOWN → trigger.close < PTB
4. Wick Check: adverse wick < body × 0.5 OR both wicks < ATR × 0.1
5. Chainlink Guard: trigger forms after 60s into window
6. Odds Ready: both poly_up_odds and poly_down_odds present
7. Window State: not already signaled or traded
"""
from dataclasses import dataclass
from typing import Optional

from polymarket_python.models import AppState, Candle, Signal, SignalDirection
from polymarket_python.state import get_signal_ptb
from polymarket_python.indicators import check_wick
from polymarket_python.scheduler import window_elapsed_ms
from polymarket_python.config import FIRST_TRIGGER_DELAY_MS, NO_TRADE_CUTOFF_SECS


@dataclass
class SignalRejection:
    reason: str


def detect_trend(candles: list[Candle]) -> str:
    """Detect trend from last 3 candles. Bullish: last_close > 3rd-back open."""
    if len(candles) < 3:
        return "Flat"
    last_close = candles[-1].close
    third_open = candles[-3].open
    if last_close > third_open:
        return "Bullish"
    elif last_close < third_open:
        return "Bearish"
    return "Flat"


def get_inside_window_candles(state: AppState) -> list[Candle]:
    """Return all candles that opened inside the current window."""
    window_start = state.window.window_start_ms
    return [c for c in state.klines if c.open_time_ms >= window_start]


def find_trigger_candle(state: AppState) -> Optional[Candle]:
    """Find the trigger candle (3rd closed candle inside window, at index 2)."""
    inside = get_inside_window_candles(state)
    if len(inside) >= 3:
        return inside[2]  # 3rd candle (0-indexed)
    return None


def check_candle_color_matches_trend(candle: Candle, trend: str) -> bool:
    if trend == "Bullish":
        return candle.color.value == "green"
    elif trend == "Bearish":
        return candle.color.value == "red"
    return False


def evaluate_signal(state: AppState, now_ms: int) -> tuple[Optional[Signal], Optional[SignalRejection]]:
    """Evaluate Strategy B signal. Returns (signal, rejection)."""
    window = state.window

    if window.window_start_ms == 0:
        return None, SignalRejection("WindowUnset")
    if window.traded:
        return None, SignalRejection("AlreadyTraded")
    if window.signal_evaluated:
        return None, SignalRejection("AlreadySignaled")

    signal_ptb = get_signal_ptb(state)
    if signal_ptb <= 0:
        return None, SignalRejection("PtbNotReady")

    elapsed_ms = window_elapsed_ms(now_ms, window.window_start_ms)
    elapsed_s = elapsed_ms // 1000

    # Guard: no signals in final 90s
    if elapsed_s >= (5 * 60) - NO_TRADE_CUTOFF_SECS:
        return None, SignalRejection("ChainlinkGuard")

    # Guard: first 60s — chainlink guard
    if elapsed_ms < FIRST_TRIGGER_DELAY_MS:
        return None, SignalRejection("TooEarly")

    # Get first 3 candles inside window for trend
    inside = get_inside_window_candles(state)
    if len(inside) < 3:
        return None, SignalRejection("NotEnoughCandles")

    trend_candles = inside[:3]
    trigger = find_trigger_candle(state)
    if trigger is None:
        return None, SignalRejection("TriggerNotReady")

    indicators = state.indicators
    if not indicators.valid:
        return None, SignalRejection("IndicatorsInvalid")

    trend = detect_trend(trend_candles)
    if trend == "Flat":
        return None, SignalRejection("TrendFlat")

    if not check_candle_color_matches_trend(trigger, trend):
        return None, SignalRejection("ColorMismatch")

    if trigger.body <= 0:
        return None, SignalRejection("TriggerDoji")

    if not check_wick(trigger, indicators.atr):
        return None, SignalRejection("WickFailed")

    # PTB breakout — UP or DOWN
    if trend == "Bullish" and trigger.close > signal_ptb:
        reason = "B_Breakout_UP_PTB"
        signal = Signal(
            direction=SignalDirection.UP,
            reason=reason,
            trigger_candle=trigger,
            ptb_used=signal_ptb,
            trend=trend,
            atr=indicators.atr,
            vol_sma=indicators.vol_sma,
        )
        return signal, None

    if trend == "Bearish" and trigger.close < signal_ptb:
        reason = "B_Breakout_DN_PTB"
        signal = Signal(
            direction=SignalDirection.DOWN,
            reason=reason,
            trigger_candle=trigger,
            ptb_used=signal_ptb,
            trend=trend,
            atr=indicators.atr,
            vol_sma=indicators.vol_sma,
        )
        return signal, None

    return None, SignalRejection("PtbSideFailed")
