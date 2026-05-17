"""Window state management — reset, PTB capture, first-in-window tracking."""
from polymarket_python.models import AppState, Candle
from polymarket_python.scheduler import calculate_window_start


def reset_window(state: AppState, window_start_ms: int) -> None:
    state.window.reset(window_start_ms)


def capture_ptb_from_binance(state: AppState, price: float, now_ms: int) -> None:
    if state.window.ptb == 0.0:
        state.window.ptb = price
        state.window.ptb_source = "BINANCE_WINDOW_OPEN"
    state.window.ptb_binance = price


def capture_ptb_from_chainlink(state: AppState, price: float, now_ms: int) -> None:
    if state.window.ptb == 0.0:
        state.window.ptb = price
        state.window.ptb_source = "CHAINLINK_WINDOW_OPEN"
    state.window.ptb_chainlink = price


def record_first_in_window(state: AppState, candle: Candle) -> None:
    if state.window.first_in_window_candle_ms == 0:
        state.window.first_in_window_candle_ms = candle.open_time_ms


def get_signal_ptb(state: AppState) -> float:
    if state.window.ptb_binance > 0:
        return state.window.ptb_binance
    return state.window.ptb if state.window.ptb > 0 else 0.0