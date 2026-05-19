"""
Strategy T+3 — 5m BTC Breakout, fires ~5 seconds before 3rd candle closes.

Rules:
1. PTB captured at T+0 (window open)
2. Trend: Candles T+1, T+2, T+3 must ALL be the same color (homogeneous)
   - All green  → Bullish
   - All red    → Bearish
   - Mixed      → NO TRADE
3. Trigger: Candle 3 (T+3)
4. Fire window: when current time >= (trigger close time − 5 seconds)
5. BUY UP:   all 3 green + price > PTB at fire time
6. BUY DOWN: all 3 red  + price < PTB at fire time
7. Wick/body checks on trigger (Candle 3)
8. Cutoff guard: no signals after T+210s
"""
from dataclasses import dataclass
from typing import Optional

from polymarket_python.models import AppState, Candle, Signal, SignalDirection
from polymarket_python.state import get_signal_ptb
from polymarket_python.indicators import check_wick
from polymarket_python.scheduler import window_elapsed_ms
from polymarket_python.config import NO_TRADE_CUTOFF_SECS

# Fire trigger 5 seconds before Candle 3 closes
TRIGGER_CANDLE_INDEX = 2          # Candle 3 (0-indexed: T+1=0, T+2=1, T+3=2)
TRIGGER_CLOSE_ADVANCE_MS = 5_000  # 5 seconds before close


@dataclass
class SignalRejection:
    reason: str


def get_inside_window_candles(state: AppState) -> list[Candle]:
    """Return all candles that opened inside the current window."""
    window_start = state.window.window_start_ms
    return [c for c in state.klines if c.open_time_ms >= window_start]


def check_homogeneous(candles: list[Candle]) -> tuple[bool, str]:
    """
    Return (is_homogeneous, trend).
    trend: "Bullish", "Bearish", or "Flat".
    "Flat" is returned when not enough candles or colors are mixed.
    """
    if len(candles) < 3:
        return False, "Flat"

    colors = [c.color.value for c in candles]
    if colors == ["green", "green", "green"]:
        return True, "Bullish"
    elif colors == ["red", "red", "red"]:
        return True, "Bearish"
    else:
        return False, "Flat"


def is_trigger_ready(now_ms: int, trigger: Candle) -> bool:
    """Return True if we are within the fire window for the trigger candle."""
    trigger_close_ms = trigger.open_time_ms + 60_000
    return now_ms >= trigger_close_ms - TRIGGER_CLOSE_ADVANCE_MS


def evaluate_signal_T3(state: AppState, now_ms: int) -> tuple[Optional[Signal], Optional[SignalRejection]]:
    """Evaluate T+3 strategy signal. Returns (signal, rejection)."""
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
        return None, SignalRejection("CutoffGuard")

    # Get first 3 candles inside window (T+1, T+2, T+3)
    inside = get_inside_window_candles(state)
    if len(inside) < 3:
        return None, SignalRejection("NotEnoughCandles")

    trend_candles = inside[:3]  # T+1, T+2, T+3

    # Check homogeneity: all 3 must be the same color
    homogeneous, trend = check_homogeneous(trend_candles)
    if not homogeneous:
        return None, SignalRejection("MixedColors")

    # Trigger is Candle 3 (T+3)
    trigger = trend_candles[TRIGGER_CANDLE_INDEX]

    # Check fire window: within 5s of trigger close
    if not is_trigger_ready(now_ms, trigger):
        return None, SignalRejection("TooEarly")

    indicators = state.indicators
    if not indicators.valid:
        return None, SignalRejection("IndicatorsInvalid")

    # Check trigger color matches trend
    if trend == "Bullish" and trigger.color.value != "green":
        return None, SignalRejection("ColorMismatch")
    if trend == "Bearish" and trigger.color.value != "red":
        return None, SignalRejection("ColorMismatch")

    # Doji check
    if trigger.body <= 0:
        return None, SignalRejection("TriggerDoji")

    # Wick check
    if not check_wick(trigger, indicators.atr):
        return None, SignalRejection("WickFailed")

    # Determine price at fire time:
    # - If trigger is still forming (not yet closed): use state.last_price
    # - If trigger is closed: use trigger.close
    trigger_close_ms = trigger.open_time_ms + 60_000
    if now_ms < trigger_close_ms:
        # Trigger still forming — use latest streaming price
        fire_price = state.last_price
    else:
        # Trigger closed — use confirmed close
        fire_price = trigger.close

    # PTB breakout check
    if trend == "Bullish" and fire_price > signal_ptb:
        reason = "T3_Breakout_UP"
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

    if trend == "Bearish" and fire_price < signal_ptb:
        reason = "T3_Breakout_DN"
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