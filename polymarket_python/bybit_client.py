"""Bybit public market data WebSocket for BTCUSDT ticker and 1m kline data."""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Awaitable, Callable

import certifi
import httpx
import websockets

from polymarket_python.config import BYBIT_REST_URL, BYBIT_SSL_VERIFY, BYBIT_SYMBOL, BYBIT_WS_URL
from polymarket_python.models import AppState, Candle, CandleColor

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


def candle_from_bybit_kline(kline: dict) -> Candle | None:
    try:
        open_price = float(kline["open"])
        close_price = float(kline["close"])
        candle = Candle(
            open=open_price,
            close=close_price,
            high=float(kline["high"]),
            low=float(kline["low"]),
            volume=float(kline.get("volume") or 0),
            open_time_ms=int(kline["start"]),
        )
        if close_price > open_price:
            candle.color = CandleColor.GREEN
        elif close_price < open_price:
            candle.color = CandleColor.RED
        else:
            candle.color = CandleColor.DOJI
        return candle
    except (KeyError, TypeError, ValueError):
        return None


def parse_kline(message: dict, symbol: str = BYBIT_SYMBOL, interval: str = "1") -> Candle | None:
    """Extract a Bybit V5 kline candle from kline interval messages."""
    if message.get("topic") != f"kline.{interval}.{symbol.upper()}":
        return None

    data = message.get("data")
    if isinstance(data, list) and data:
        return candle_from_bybit_kline(data[0])
    if isinstance(data, dict):
        return candle_from_bybit_kline(data)
    return None


class BybitClient:
    """Subscribe to Bybit V5 public ticker and kline updates."""

    def __init__(
        self,
        state: AppState | None = None,
        symbol: str = BYBIT_SYMBOL,
        ws_url: str = BYBIT_WS_URL,
        on_price: Callable[[float], Awaitable[None]] | None = None,
        on_candle: Callable[[Candle], Awaitable[None]] | None = None,
    ):
        self.state = state
        self.symbol = symbol.upper()
        self.ws_url = ws_url
        self.on_price = on_price
        self.on_candle = on_candle
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not BYBIT_SSL_VERIFY:
            logger.warning("[BYBIT] TLS certificate verification is disabled for this process")
        await self._fetch_seed_klines()
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
        ticker_topic = f"tickers.{self.symbol}"
        kline_topic = f"kline.1.{self.symbol}"
        subscribe_msg = {"op": "subscribe", "args": [ticker_topic, kline_topic]}

        while self._running:
            try:
                if BYBIT_SSL_VERIFY:
                    ctx = ssl.create_default_context(cafile=certifi.where())
                else:
                    ctx = ssl._create_unverified_context()
                async with websockets.connect(self.ws_url, ssl=ctx, ping_interval=20) as ws:
                    logger.info("[BYBIT] WS connected: %s", self.ws_url)
                    await ws.send(json.dumps(subscribe_msg))
                    logger.info("[BYBIT] Subscribed to %s, %s", ticker_topic, kline_topic)

                    async for raw in ws:
                        if not self._running:
                            break

                        msg = json.loads(raw)
                        if msg.get("op") == "subscribe":
                            logger.info("[BYBIT] Subscription response: %s", msg)
                            continue

                        candle = parse_kline(msg, self.symbol)
                        if candle:
                            if self.state:
                                self.state.push_kline(candle)
                                self.state.last_kline_time_ms = candle.open_time_ms
                            if self.on_candle:
                                await self.on_candle(candle)
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
                logger.warning("[BYBIT] WS error: %r, reconnecting in 5s...", e)
                await asyncio.sleep(5)

    async def _fetch_seed_klines(self, limit: int = 60) -> None:
        if self.state is None:
            return

        try:
            verify = certifi.where() if BYBIT_SSL_VERIFY else False
            async with httpx.AsyncClient(timeout=15, verify=verify) as client:
                resp = await client.get(
                    f"{BYBIT_REST_URL}/v5/market/kline",
                    params={
                        "category": "linear",
                        "symbol": self.symbol,
                        "interval": "1",
                        "limit": limit,
                    },
                )
                resp.raise_for_status()
                result = resp.json().get("result", {})
                rows = result.get("list") or []
                for row in reversed(rows):
                    if len(row) < 6:
                        continue
                    candle = Candle(
                        open_time_ms=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                    if candle.close > candle.open:
                        candle.color = CandleColor.GREEN
                    elif candle.close < candle.open:
                        candle.color = CandleColor.RED
                    else:
                        candle.color = CandleColor.DOJI
                    self.state.push_kline(candle)
                    self.state.last_kline_time_ms = candle.open_time_ms
                logger.info("[BYBIT] Seeded %s candles", len(rows))
        except Exception as e:
            logger.warning("[BYBIT] Kline seed failed: %s", e)
