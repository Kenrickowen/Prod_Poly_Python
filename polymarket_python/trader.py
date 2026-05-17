"""Trade execution — convert Signal to Polymarket order."""
import logging
import time

from polymarket_python.models import AppState, Signal, SignalDirection, Trade
from polymarket_python.polymarket_client import PolymarketClient
from polymarket_python.config import CAPITAL, POSITION_FRACTION

logger = logging.getLogger(__name__)


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

        # Position size: 1% of capital
        size = (CAPITAL * POSITION_FRACTION) / odds
        logger.info(
            f"[TRADER] {direction.value}: size={size:.2f} tokens at price={odds:.4f}, "
            f"token_id={token_id}, reason={signal.reason}"
        )

        side = "BUY" if direction == SignalDirection.UP else "BUY"
        result = await self.client.place_order(token_id, side, size, odds)

        if result:
            trade = Trade(
                timestamp_ms=int(time.time() * 1000),
                direction=direction,
                token_id=token_id,
                price=odds,
                size=size,
                pnl=0.0,
                settled=False,
            )
            state.add_trade(trade)
            state.window.traded = True
            state.window.signal_evaluated = True
            logger.info(f"[TRADER] Trade SUCCESS — {direction.value}")
            return True
        else:
            logger.error(f"[TRADER] Trade FAILED — {direction.value}")
            return False