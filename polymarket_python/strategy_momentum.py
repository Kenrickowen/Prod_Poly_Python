"""Momentum mispricing strategy for BTC 5-minute UP/DOWN markets."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import pstdev
from typing import Optional

from polymarket_python.config import (
    MOMENTUM_CHAINLINK_MAX_DEVIATION,
    MOMENTUM_EDGE_THRESHOLD,
    MOMENTUM_EXIT_BEFORE_CLOSE_SECS,
    MOMENTUM_MAX_SPREAD,
    MOMENTUM_MIN_ELAPSED_SECS,
    MOMENTUM_PAPER_ONLY,
    WINDOW_MS,
)
from polymarket_python.models import AppState, Signal, SignalDirection
from polymarket_python.scheduler import window_elapsed_ms, window_remaining_ms
from polymarket_python.state import get_signal_ptb


@dataclass
class SignalRejection:
    reason: str


def normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def realized_return_volatility(closes: list[float], lookback: int = 10) -> float:
    prices = [p for p in closes[-lookback:] if p > 0]
    if len(prices) < 3:
        return 0.0

    returns = []
    for previous, current in zip(prices, prices[1:]):
        if previous > 0 and current > 0:
            returns.append(math.log(current / previous))
    if len(returns) < 2:
        return 0.0
    return pstdev(returns)


def fair_up_probability(current_price: float, open_price: float, minute_volatility: float, remaining_ms: int) -> float:
    if current_price <= 0 or open_price <= 0:
        return 0.5

    remaining_minutes = max(remaining_ms / 60_000, 1 / 60)
    if minute_volatility <= 0:
        return 0.99 if current_price > open_price else 0.01 if current_price < open_price else 0.5

    denominator = current_price * minute_volatility * math.sqrt(remaining_minutes)
    if denominator <= 0:
        return 0.5

    z_score = (current_price - open_price) / denominator
    return min(max(normal_cdf(z_score), 0.001), 0.999)


def _set_diagnostics(state: AppState, **values) -> None:
    state.momentum_diagnostics = values


def evaluate_signal_momentum(state: AppState, now_ms: int) -> tuple[Optional[Signal], Optional[SignalRejection]]:
    window = state.window
    if window.window_start_ms == 0:
        _set_diagnostics(state, reason="WindowUnset")
        return None, SignalRejection("WindowUnset")
    if window.traded:
        _set_diagnostics(state, reason="AlreadyTraded")
        return None, SignalRejection("AlreadyTraded")
    if window.signal_evaluated:
        _set_diagnostics(state, reason="AlreadySignaled")
        return None, SignalRejection("AlreadySignaled")

    elapsed_s = window_elapsed_ms(now_ms, window.window_start_ms) // 1000
    remaining_ms = window_remaining_ms(now_ms, window.window_start_ms)
    if elapsed_s < MOMENTUM_MIN_ELAPSED_SECS:
        _set_diagnostics(state, elapsed_s=elapsed_s, reason="TooEarly")
        return None, SignalRejection("TooEarly")
    if remaining_ms <= MOMENTUM_EXIT_BEFORE_CLOSE_SECS * 1000:
        _set_diagnostics(state, remaining_ms=remaining_ms, reason="FinalSeconds")
        return None, SignalRejection("FinalSeconds")

    open_price = get_signal_ptb(state)
    current_price = state.last_price
    up_odds = state.poly_up_odds
    down_odds = state.poly_down_odds
    if open_price <= 0:
        _set_diagnostics(state, reason="PtbNotReady")
        return None, SignalRejection("PtbNotReady")
    if current_price <= 0:
        _set_diagnostics(state, reason="PriceNotReady")
        return None, SignalRejection("PriceNotReady")
    if up_odds is None or down_odds is None or up_odds <= 0 or down_odds <= 0:
        _set_diagnostics(state, reason="OddsNotReady")
        return None, SignalRejection("OddsNotReady")

    spread_proxy = abs((up_odds + down_odds) - 1.0)
    if spread_proxy > MOMENTUM_MAX_SPREAD:
        _set_diagnostics(state, spread=spread_proxy, reason="SpreadTooWide")
        return None, SignalRejection("SpreadTooWide")

    chainlink_divergence = None
    if state.chainlink_price and state.chainlink_price > 0:
        chainlink_divergence = abs(current_price - state.chainlink_price) / state.chainlink_price
        if chainlink_divergence > MOMENTUM_CHAINLINK_MAX_DEVIATION:
            _set_diagnostics(
                state,
                chainlink_divergence=chainlink_divergence,
                reason="ChainlinkDivergence",
            )
            return None, SignalRejection("ChainlinkDivergence")

    closes = [c.close for c in state.klines if c.close > 0]
    if not closes or closes[-1] != current_price:
        closes.append(current_price)
    minute_volatility = realized_return_volatility(closes)
    fair_up = fair_up_probability(current_price, open_price, minute_volatility, remaining_ms)
    fair_down = 1.0 - fair_up
    up_edge = fair_up - up_odds
    down_edge = fair_down - down_odds
    direction = None
    edge = 0.0
    market_probability = 0.0
    fair_probability = 0.0

    if up_edge >= MOMENTUM_EDGE_THRESHOLD and up_edge >= down_edge:
        direction = SignalDirection.UP
        edge = up_edge
        market_probability = up_odds
        fair_probability = fair_up
    elif down_edge >= MOMENTUM_EDGE_THRESHOLD:
        direction = SignalDirection.DOWN
        edge = down_edge
        market_probability = down_odds
        fair_probability = fair_down

    _set_diagnostics(
        state,
        fair_up=fair_up,
        fair_down=fair_down,
        market_up=up_odds,
        market_down=down_odds,
        up_edge=up_edge,
        down_edge=down_edge,
        spread=spread_proxy,
        minute_volatility=minute_volatility,
        chainlink_divergence=chainlink_divergence,
        paper_only=MOMENTUM_PAPER_ONLY,
        reason="Signal" if direction else "EdgeTooSmall",
    )

    if direction is None:
        return None, SignalRejection("EdgeTooSmall")

    return Signal(
        direction=direction,
        reason=f"MomentumMispricing_{direction.value}",
        ptb_used=open_price,
        trend="Momentum",
        paper_only=MOMENTUM_PAPER_ONLY,
        fair_probability=fair_probability,
        market_probability=market_probability,
        edge=edge,
    ), None
