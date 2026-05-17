"""5-minute window timing calculations."""
from polymarket_python.config import WINDOW_MS, WINDOW_MINUTES


def calculate_window_start(now_ms: int) -> int:
    return (now_ms // WINDOW_MS) * WINDOW_MS


def calculate_next_window_start(now_ms: int) -> int:
    return calculate_window_start(now_ms) + WINDOW_MS


def window_elapsed_ms(now_ms: int, window_start_ms: int) -> int:
    return max(0, now_ms - window_start_ms)


def window_remaining_ms(now_ms: int, window_start_ms: int) -> int:
    return max(0, WINDOW_MS - window_elapsed_ms(now_ms, window_start_ms))


def is_window_boundary(now_ms: int, window_start_ms: int) -> bool:
    return (now_ms - window_start_ms) >= WINDOW_MS


def is_final_seconds(now_ms: int, window_start_ms: int, cutoff_secs: int = 90) -> bool:
    remaining = window_remaining_ms(now_ms, window_start_ms)
    return remaining < cutoff_secs * 1000