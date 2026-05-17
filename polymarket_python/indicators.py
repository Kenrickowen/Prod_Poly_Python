"""ATR and volume SMA indicators."""
from polymarket_python.config import ATR_PERIOD, VOL_SMA_PERIOD
from polymarket_python.models import AppState, Candle


def compute_atr(candles: list[Candle], period: int = ATR_PERIOD) -> float:
    if len(candles) < period:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        c = candles[i]
        p = candles[i - 1]
        tr = max(
            c.high - c.low,
            abs(c.high - p.close),
            abs(c.low - p.close),
        )
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / period


def compute_vol_sma(candles: list[Candle], period: int = VOL_SMA_PERIOD) -> float:
    if len(candles) < period:
        return 0.0
    return sum(c.volume for c in candles[-period:]) / period


def update_indicators(state: AppState) -> None:
    if len(state.klines) < ATR_PERIOD:
        state.indicators.valid = False
        return
    state.indicators.atr = compute_atr(state.klines)
    state.indicators.vol_sma = compute_vol_sma(state.klines)
    state.indicators.valid = state.indicators.atr > 0 and state.indicators.vol_sma > 0


def check_wick(candle: Candle, atr: float) -> bool:
    upper = candle.upper_wick
    lower = candle.lower_wick
    body = candle.body
    if body <= 0:
        return False
    return (upper < body * 0.5 or lower < body * 0.5) or (upper < atr * 0.1 and lower < atr * 0.1)