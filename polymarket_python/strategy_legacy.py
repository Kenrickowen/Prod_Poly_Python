"""
Strategy B — Legacy (from Rust breakout.rs).

Differences from current strategy:
1. Trend candles: last 3 candles BEFORE window start (pre-window), not inside window
2. Trigger candle: FIRST candle inside window (not 4th)
3. Wick check: wick < body × 2.0 OR wick < atr × 0.3
4. Volume check: does NOT reject signal — only changes reason code
5. Signal reasons: B_VolBreakout_UP_PTB, B_Breakout_UP_PTB, etc.
6. PTB preference: ptb_binance if available, else ptb
"""
from dataclasses import dataclass
from typing import Optional

from polymarket_python.models import AppState, Candle, Signal, SignalDirection
from polymarket_python.state import get_signal_ptb
from polymarket_python.scheduler import window_elapsed_ms, WINDOW_MS


@dataclass
class SignalRejection:
    reason: str


# Legacy wick multiplier and ATR factor
LEGACY_WICK_BODY_MULTIPLIER = 2.0
LEGACY_ATR_WICK_FACTOR = 0.3


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


def get_trend_candles_legacy(klines: list[Candle], window_start_ms: int) -> list[Candle]:
    """Get last 3 candles BEFORE window start (pre-window candles)."""
    pre_window = [c for c in klines if c.open_time_ms < window_start_ms]
    if len(pre_window) < 3:
        return []
    return pre_window[-3:]


def find_trigger_candle_legacy(klines: list[Candle], window_start_ms: int) -> Optional[Candle]:
    """Find first candle inside window (legacy trigger)."""
    inside = [c for c in klines if c.open_time_ms >= window_start_ms]
    return inside[0] if inside else None


def check_wick_legacy(candle: Candle, trend: str, atr: float) -> bool:
    """Legacy wick check: wick < body × 2.0 OR wick < atr × 0.3."""
    body = candle.body
    if body <= 0:
        return False
    upper = candle.upper_wick
    lower = candle.lower_wick
    atr_ok = atr > 0.0 and upper < atr * LEGACY_ATR_WICK_FACTOR and lower < atr * LEGACY_ATR_WICK_FACTOR
    if trend == "Bullish":
        return upper < body * LEGACY_WICK_BODY_MULTIPLIER or atr_ok
    elif trend == "Bearish":
        return lower < body * LEGACY_WICK_BODY_MULTIPLIER or atr_ok
    return False


def strategy_b_reason(trend: str, volume_ok: bool) -> str:
    """Return signal reason string based on trend and volume."""
    if trend == "Bullish":
        return "B_VolBreakout_UP_PTB" if volume_ok else "B_Breakout_UP_PTB"
    elif trend == "Bearish":
        return "B_VolBreakout_DN_PTB" if volume_ok else "B_Breakout_DN_PTB"
    return "B_Flat"


def get_signal_ptb_legacy(state: AppState) -> float:
    """Legacy PTB: prefers ptb_binance if available, else ptb."""
    if state.window.ptb_binance > 0:
        return state.window.ptb_binance
    return state.window.ptb if state.window.ptb > 0 else 0.0


def check_candle_color_matches_trend(candle: Candle, trend: str) -> bool:
    if trend == "Bullish":
        return candle.color.value == "green"
    elif trend == "Bearish":
        return candle.color.value == "red"
    return False


def evaluate_signal_legacy(state: AppState, now_ms: int) -> tuple[Optional[Signal], Optional[SignalRejection]]:
    """Evaluate legacy Strategy B signal."""
    window = state.window

    if window.window_start_ms == 0:
        return None, SignalRejection("WindowUnset")
    if window.traded:
        return None, SignalRejection("AlreadyTraded")
    if window.signal_evaluated:
        return None, SignalRejection("AlreadySignaled")

    ptb = get_signal_ptb_legacy(state)
    if ptb <= 0:
        return None, SignalRejection("PtbNotReady")

    elapsed_ms = window_elapsed_ms(now_ms, window.window_start_ms)
    elapsed_s = elapsed_ms // 1000

    # No trades in final 90s
    if elapsed_s >= (5 * 60) - 90:
        return None, SignalRejection("ChainlinkGuard")

    # First 60s: chainlink guard
    if elapsed_ms < 60_000:
        return None, SignalRejection("TooEarly")

    # Get trend candles (last 3 BEFORE window)
    trend_candles = get_trend_candles_legacy(state.klines, window.window_start_ms)
    if len(trend_candles) < 3:
        return None, SignalRejection("NotEnoughCandles")

    # Get trigger candle (first inside window)
    trigger = find_trigger_candle_legacy(state.klines, window.window_start_ms)
    if trigger is None:
        return None, SignalRejection("TriggerNotReady")

    indicators = state.indicators
    if not indicators.valid:
        return None, SignalRejection("IndicatorsInvalid")

    trend = detect_trend(trend_candles)
    if trend == "Flat":
        return None, SignalRejection("TrendFlat")

    if trigger.body <= 0:
        return None, SignalRejection("TriggerDoji")

    if not check_candle_color_matches_trend(trigger, trend):
        return None, SignalRejection("ColorMismatch")

    if not check_wick_legacy(trigger, trend, indicators.atr):
        return None, SignalRejection("WickFailed")

    # Volume check — does NOT reject, only affects reason
    volume_ok = indicators.valid and trigger.volume > indicators.vol_sma * 1.0

    # PTB breakout check
    reason = strategy_b_reason(trend, volume_ok)
    if trend == "Bullish" and trigger.close > ptb:
        signal = Signal(
            direction=SignalDirection.UP,
            reason=reason,
            trigger_candle=trigger,
            ptb_used=ptb,
            trend=trend,
            atr=indicators.atr,
            vol_sma=indicators.vol_sma,
        )
        return signal, None

    if trend == "Bearish" and trigger.close < ptb:
        signal = Signal(
            direction=SignalDirection.DOWN,
            reason=reason,
            trigger_candle=trigger,
            ptb_used=ptb,
            trend=trend,
            atr=indicators.atr,
            vol_sma=indicators.vol_sma,
        )
        return signal, None

    return None, SignalRejection("PtbSideFailed")