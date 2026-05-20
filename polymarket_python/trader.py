"""Trade execution — convert Signal to Polymarket order."""
import logging
import time

from polymarket_python.models import AppState, Signal, SignalDirection, Trade
from polymarket_python.polymarket_client import PolymarketClient
from polymarket_python.config import CAPITAL
from polymarket_python.trade_store import append_trade

logger = logging.getLogger(__name__)


def account_equity(state: AppState) -> float:
    cash = state.current_balance if state.wallet_pusd_balance is not None else 0.0
    open_cost_basis = sum(
        trade.size
        for trade in state.trade_history
        if not trade.settled and not trade.redemption_tx
    )
    return cash + open_cost_basis


def calculate_position_size_usd(state: AppState) -> float:
    if state.position_size_mode == "percent":
        equity = account_equity(state)
        if equity <= 0:
            equity = state.initial_balance if state.initial_balance > 0 else CAPITAL
        spend = equity * max(state.position_equity_percent, 0.0) / 100
    else:
        spend = max(state.position_fixed_usd, 0.0)

    if state.wallet_pusd_balance is not None:
        spend = min(spend, max(state.current_balance, 0.0))
    return spend


class Trader:
    def __init__(self, client: PolymarketClient, token_id_up: str, token_id_down: str):
        self.client = client
        self.token_id_up = token_id_up
        self.token_id_down = token_id_down

    async def on_signal(self, state: AppState, signal: Signal) -> bool:
        """Execute trade based on signal. Returns True on success."""
        direction = signal.direction
        token_id = self.token_id_up if direction == SignalDirection.UP else self.token_id_down

        if not token_id:
            logger.error(f"[TRADER] No token_id for {direction.value}")
            return False

        # Get odds for this token
        odds = await self.client.get_odds(token_id)
        if odds is None:
            logger.warning(f"[TRADER] Could not get odds for {token_id}")
            odds = 0.5  # fallback

        spend_usd = calculate_position_size_usd(state)
        if spend_usd <= 0:
            logger.warning("[TRADER] Position size is zero; skipping trade")
            return False
        size = spend_usd / odds
        logger.info(
            f"[TRADER] {direction.value}: spend=${spend_usd:.2f}, size={size:.2f} tokens at price={odds:.4f}, "
            f"token_id={token_id}, reason={signal.reason}"
        )

        side = "BUY" if direction == SignalDirection.UP else "SELL"
        result = await self.client.place_market_order(token_id, side, spend_usd)

        if result:
            order_id = ""
            if isinstance(result, dict):
                order_id = str(result.get("orderID") or result.get("orderId") or result.get("id") or "")
            trigger = signal.trigger_candle
            trade = Trade(
                timestamp_ms=int(time.time() * 1000),
                direction=direction,
                token_id=token_id,
                price=odds,
                size=spend_usd,
                condition_id=state.poly_market_condition_id,
                market_slug=state.poly_market_slug,
                order_id=order_id,
                signal_reason=signal.reason,
                signal_trend=signal.trend,
                signal_ptb=signal.ptb_used,
                trigger_open=trigger.open if trigger else 0.0,
                trigger_close=trigger.close if trigger else 0.0,
                trigger_high=trigger.high if trigger else 0.0,
                trigger_low=trigger.low if trigger else 0.0,
                trigger_time_ms=trigger.open_time_ms if trigger else 0,
                token_id_up=self.token_id_up,
                token_id_down=self.token_id_down,
                neg_risk=state.poly_market_neg_risk,
                pnl=0.0,
                settled=False,
            )
            state.add_trade(trade)
            append_trade(trade)
            state.window.traded = True
            state.window.signal_evaluated = True
            logger.info(f"[TRADER] Trade SUCCESS — {direction.value}")
            return True
        else:
            logger.error(f"[TRADER] Trade FAILED — {direction.value}")
            return False
