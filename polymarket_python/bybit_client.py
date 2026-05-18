"""Bybit public market data WebSocket for BTCUSDT ticker prices."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets

from polymarket_python.config import BYBIT_SYMBOL, BYBIT_WS_URL
from polymarket_python.models import AppState

logger = logging.getLogger(__name__)


def parse_ticker_price(message: dict, symbol: str = BYBIT_SYMBOL) -> float | None:
    """Extract lastPrice from a Bybit V5 ticker snapshot/delta message."""
    if message.get("topic") != f"tickers.{symbol.upper()}":
        return None

    data = message.get("data")
    if not isinstance(data, dict):
        return None

    price = data.get("lastPrice")
    if price in (None, ""):
        return None

    try:
        return float(price)
    except (TypeError, ValueError):
        return None


class BybitClient:
    """Subscribe to Bybit V5 public ticker updates and stream last prices."""

    def __init__(
        self,
        state: AppState | None = None,
        symbol: str = BYBIT_SYMBOL,
        ws_url: str = BYBIT_WS_URL,
        on_price: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.state = state
        self.symbol = symbol.upper()
        self.ws_url = ws_url
        self.on_price = on_price
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        topic = f"tickers.{self.symbol}"
        subscribe_msg = {"op": "subscribe", "args": [topic]}

        while self._running:
            try:
                async with websockets.connect(self.ws_url, ping_interval=20) as ws:
                    logger.info("[BYBIT] WS connected: %s", self.ws_url)
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("[BYBIT] Subscribed to %s", topic)

                    async for raw in ws:
                        if not self._running:
                            break

                        msg = json.loads(raw)
                        if msg.get("op") == "subscribe":
                            logger.info("[BYBIT] Subscription response: %s", msg)
                            continue

                        price = parse_ticker_price(msg, self.symbol)
                        if price is None:
                            continue

                        if self.state:
                            self.state.last_price = price
                            self.state.price_source = "Bybit WebSocket"
                            self.state.last_ticker_time_ms = int(msg.get("ts") or 0)

                        if self.on_price:
                            await self.on_price(price)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("[BYBIT] WS error: %s, reconnecting in 5s...", e)
                await asyncio.sleep(5)
