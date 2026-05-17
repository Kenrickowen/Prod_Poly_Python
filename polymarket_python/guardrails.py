"""Time-based trade restrictions."""
from polymarket_python.config import NO_TRADE_CUTOFF_SECS, CHAINLINK_GUARD_SECS, WINDOW_MINUTES
from polymarket_python.scheduler import window_remaining_ms, window_elapsed_ms


def should_trade(now_ms: int, window_start_ms: int) -> tuple[bool, str]:
    """Returns (can_trade, reason). reason is empty if can_trade=True."""
    if window_start_ms == 0:
        return False, "WindowUnset"

    elapsed_s = window_elapsed_ms(now_ms, window_start_ms) // 1000

    # First 60s: chainlink guard
    if elapsed_s < CHAINLINK_GUARD_SECS:
        return False, "TooEarly"

    # Final 90s: no trades
    remaining = window_remaining_ms(now_ms, window_start_ms)
    if remaining < NO_TRADE_CUTOFF_SECS * 1000:
        return False, "FinalSeconds"

    return True, ""


def check_price_disagreement(binance_price: float, chainlink_price: float, threshold: float = 0.02) -> bool:
    """Return True if disagreement > threshold%."""
    if chainlink_price <= 0:
        return False
    diff = abs(binance_price - chainlink_price) / chainlink_price
    return diff > threshold