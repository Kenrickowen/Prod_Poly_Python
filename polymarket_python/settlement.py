"""Resolved-market settlement helpers for trade PnL accounting."""
from __future__ import annotations

from polymarket_python.models import AppState, Trade
from polymarket_python.polymarket_public_client import BtcMarket


def _token_payout(trade: Trade, market: BtcMarket) -> float | None:
    if market.gamma_up_odds is None or market.gamma_down_odds is None:
        return None

    if trade.token_id and trade.token_id == market.token_id_up:
        return market.gamma_up_odds
    if trade.token_id and trade.token_id == market.token_id_down:
        return market.gamma_down_odds
    if trade.direction.value == "UP":
        return market.gamma_up_odds
    if trade.direction.value == "DOWN":
        return market.gamma_down_odds
    return None


def market_has_final_payout(market: BtcMarket) -> bool:
    if not (market.resolved or market.closed):
        return False
    prices = [market.gamma_up_odds, market.gamma_down_odds]
    if any(p is None for p in prices):
        return False
    return all(0.0 <= float(p) <= 1.0 for p in prices) and abs(sum(float(p) for p in prices) - 1.0) < 0.02


def update_trade_from_resolved_market(trade: Trade, market: BtcMarket) -> bool:
    """Update one trade with realized PnL if Gamma has the final payout."""
    if trade.settled and trade.pnl != 0:
        return False
    if trade.market_slug and market.slug and trade.market_slug != market.slug:
        return False
    if not market_has_final_payout(market):
        return False

    payout = _token_payout(trade, market)
    if payout is None:
        return False

    shares = trade.size / trade.price if trade.price > 0 else 0.0
    trade.pnl = (shares * payout) - trade.size
    trade.settled = True
    return True


def recompute_trade_metrics(state: AppState) -> None:
    realized = [trade for trade in state.trade_history if trade.settled]
    state.total_pnl = sum(trade.pnl for trade in realized)
    state.win_count = sum(1 for trade in realized if trade.pnl > 0)
    state.loss_count = sum(1 for trade in realized if trade.pnl < 0)
