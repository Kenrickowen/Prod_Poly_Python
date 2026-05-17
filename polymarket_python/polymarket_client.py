"""Polymarket CLOB client using py-clob-client-v2 SDK with EOA signature type 0."""
import asyncio
import json
import logging
import os

from py_clob_client import ClobClient, OrderArgs, OrderType, PartialCreateOrderOptions
from py_order_utils.model import BUY, SELL

from polymarket_python.config import POLYMARKET_HOST, CHAIN_ID

logger = logging.getLogger(__name__)

# Signature type 0 = EOA (wallet pays its own gas)
SIGNATURE_TYPE_EOA = 0

# Polymarket WebSocket endpoint
POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PolymarketClient:
    """
    Polymarket CLOB client using official py-clob-client-v2.
    Uses EOA wallet (signature type 0) — wallet pays its own gas.
    """

    def __init__(self):
        private_key = os.getenv("PRIVATE_KEY", "")
        funder_address = os.getenv("FUNDER_ADDRESS", "")

        if not private_key or not funder_address:
            raise ValueError("PRIVATE_KEY and FUNDER_ADDRESS must be set in .env")

        self.funder_address = funder_address
        self._key = private_key

        # L1 auth — derive API credentials
        temp_client = ClobClient(
            host=POLYMARKET_HOST,
            key=self._key,
            chain_id=CHAIN_ID,
        )
        self._creds = temp_client.create_or_derive_api_creds()
        logger.info("[POLY] API credentials derived")

        # L2 auth — fully authenticated client with signature type 0 (EOA)
        self._client = ClobClient(
            host=POLYMARKET_HOST,
            key=self._key,
            chain_id=CHAIN_ID,
            creds=self._creds,
            signature_type=SIGNATURE_TYPE_EOA,
            funder=self.funder_address,
        )
        logger.info(f"[POLY] Client initialized for {self.funder_address}")

        self._ws_task: asyncio.Task | None = None
        self._ws_running = False
        self._ws_assets: list[str] = []

    def get_client(self) -> ClobClient:
        return self._client

    async def _ws_message_handler(self, msg: str) -> None:
        """Handle incoming WebSocket messages for book/ticker updates."""
        try:
            data = json.loads(msg)
            msg_type = data.get("type", "")

            if msg_type == "best_bid_ask":
                asset = data.get("asset_id", "")
                bid = data.get("bid")
                ask = data.get("ask")
                if bid and ask:
                    logger.debug(f"[POLY_WS] {asset}: bid={bid}, ask={ask}")
                    # Update odds cache
                    if hasattr(self, '_odds_cache'):
                        self._odds_cache[asset] = {"bid": float(bid), "ask": float(ask)}

            elif msg_type == "last_trade_price":
                asset = data.get("asset_id", "")
                price = data.get("price")
                if price:
                    logger.debug(f"[POLY_WS] {asset}: last_trade={price}")

        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.debug(f"[POLY_WS] message error: {e}")

    async def _ws_connect_loop(self, assets: list[str]) -> None:
        """Maintain WebSocket connection with auto-reconnect."""
        import ssl
        import certifi
        import websockets

        ctx = ssl.create_default_context()
        ctx.load_verify_locations(certifi.where())

        self._ws_assets = assets
        self._odds_cache = {asset: {"bid": 0.0, "ask": 0.0} for asset in assets}

        while self._ws_running:
            try:
                async with websockets.connect(POLYMARKET_WS_URL, ssl=ctx, ping_interval=20) as ws:
                    logger.info(f"[POLY_WS] Connected, subscribing to {len(assets)} assets")
                    subscribe_msg = {
                        "type": "subscribe",
                        "channel": "book",
                        "assets": assets,
                    }
                    await ws.send(json.dumps(subscribe_msg))

                    async for msg in ws:
                        if not self._ws_running:
                            break
                        await self._ws_message_handler(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[POLY_WS] Connection error: {e}, reconnecting in 3s...")
                await asyncio.sleep(3)

    def start_ws_feed(self, assets: list[str]) -> None:
        """Start WebSocket feed for given token IDs (non-blocking)."""
        if self._ws_task and not self._ws_task.done():
            logger.warning("[POLY_WS] Feed already running")
            return

        self._ws_running = True
        self._ws_task = asyncio.create_task(self._ws_connect_loop(assets))
        logger.info(f"[POLY_WS] Starting WebSocket feed for {assets}")

    def stop_ws_feed(self) -> None:
        """Stop the WebSocket feed gracefully."""
        self._ws_running = False
        if self._ws_task:
            self._ws_task.cancel()
            logger.info("[POLY_WS] Feed stopped")

    async def get_market(self, condition_id: str) -> dict | None:
        """Get CLOB market info by condition_id."""
        try:
            return self._client.get_clob_market_info(condition_id)
        except Exception as e:
            logger.warning(f"[POLY] get_market failed: {e}")
            return None

    async def get_odds(self, token_id: str) -> float | None:
        """Get current odds for a token from WebSocket cache, with REST fallback."""
        # Try WebSocket cache first
        if hasattr(self, '_odds_cache') and token_id in self._odds_cache:
            cached = self._odds_cache[token_id]
            if cached["bid"] > 0 and cached["ask"] > 0:
                return (cached["bid"] + cached["ask"]) / 2

        # Fallback to REST
        try:
            spread = self._client.get_spread(token_id)
            if spread:
                bid = spread.get("bid") or spread.get("best_bid")
                ask = spread.get("ask") or spread.get("best_ask")
                if bid and ask:
                    return (float(bid) + float(ask)) / 2

            mid = self._client.get_midpoint(token_id)
            if mid is not None:
                if isinstance(mid, dict):
                    return float(mid.get("mid", 0)) or None
                return float(mid) if mid else None
            return None
        except Exception as e:
            logger.debug(f"[POLY] get_odds failed for {token_id}: {e}")
            return None

    async def get_balance(self) -> float:
        """Get USDC collateral balance."""
        try:
            result = self._client.get_balance_allowance()
            return float(result.get("balance", 0))
        except Exception as e:
            logger.warning(f"[POLY] get_balance failed: {e}")
            return 0.0

    async def place_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        size: float,
        price: float,
    ) -> dict | None:
        """
        Place a GTC limit order using OrderArgs.
        Uses tick_size and neg_risk from market info.
        """
        try:
            # Get market info for tick_size and neg_risk
            market_info = self._client.get_clob_market_info(condition_id=token_id)
            tick_size = market_info.get("mts", "0.01") if market_info else "0.01"
            neg_risk = market_info.get("nr", False) if market_info else False

            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=BUY if side.upper() == "BUY" else SELL,
            )
            options = PartialCreateOrderOptions(
                tick_size=tick_size,
                neg_risk=neg_risk,
            )

            response = self._client.create_and_post_order(
                order_args=order_args,
                options=options,
                order_type=OrderType.GTC,
            )
            logger.info(f"[POLY] Order placed: {response}")
            return response
        except Exception as e:
            logger.error(f"[POLY] place_order failed: {e}")
            return None

    async def cancel_all(self) -> dict | None:
        """Cancel all open orders."""
        try:
            return self._client.cancel_all()
        except Exception as e:
            logger.warning(f"[POLY] cancel_all failed: {e}")
            return None