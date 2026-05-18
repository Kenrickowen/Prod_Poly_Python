"""Binance market data — WebSocket kline + ticker, REST seed."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Awaitable

import httpx
import websockets

from polymarket_python.config import BINANCE_WS_URL, BINANCE_REST_URL, BINANCE_SEED_CANDLES
from polymarket_python.models import AppState, Candle, CandleColor

logger = logging.getLogger(__name__)


def parse_kline(raw: dict) -> Candle | None:
    try:
        k = raw["k"]
        if not k.get("x", False):
            return None
        return Candle.from_binance_kline(k)
    except (KeyError, TypeError):
        return None


def parse_ticker(raw: dict) -> float | None:
    try:
        return float(raw["c"])
    except (KeyError, TypeError):
        return None


class BinanceClient:
    """
    Binance WebSocket for klines (1m candles) + ticker.
    Seeds historical candles on startup via REST.
    """

    def __init__(
        self,
        state: AppState,
        on_candle: Callable[[Candle], Awaitable[None]] | None = None,
        on_price: Callable[[float], Awaitable[None]] | None = None,
    ):
        self.state = state
        self.on_candle = on_candle
        self.on_price = on_price
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        await self._fetch_seed()
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

    async def _fetch_seed(self) -> None:
        url = f"{BINANCE_REST_URL}/klines"
        params = {"symbol": "BTCUSDT", "interval": "1m", "limit": BINANCE_SEED_CANDLES}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                klines = resp.json()
                for k in klines:
                    candle = Candle(
                        open=float(k[1]),
                        close=float(k[4]),
                        high=float(k[2]),
                        low=float(k[3]),
                        volume=float(k[5]),
                        open_time_ms=int(k[0]),
                    )
                    if candle.close > candle.open:
                        candle.color = CandleColor.GREEN
                    elif candle.close < candle.open:
                        candle.color = CandleColor.RED
                    else:
                        candle.color = CandleColor.DOJI
                    self.state.push_kline(candle)
                logger.info(f"[BINANCE] Seeded {len(klines)} candles")
        except Exception as e:
            logger.warning(f"[BINANCE] Seed fetch failed: {e}")

    async def _run(self) -> None:
        tasks = [
            asyncio.create_task(self._kline_loop()),
            asyncio.create_task(self._ticker_loop()),
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()

    async def _kline_loop(self) -> None:
        while self._running:
            try:
                async with websockets.connect(BINANCE_WS_URL, ping_interval=20) as ws:
                    logger.info("[BINANCE] Kline WS connected")
                    async for raw in ws:
                        msg = json.loads(raw)
                        stream = msg.get("stream", "")
                        if "kline" in stream:
                            candle = parse_kline(msg.get("data", {}))
                            if candle:
                                self.state.push_kline(candle)
                                self.state.last_kline_time_ms = candle.open_time_ms
                                if self.on_candle:
                                    await self.on_candle(candle)
                        elif "ticker" in stream:
                            price = parse_ticker(msg.get("data", {}))
                            if price:
                                self.state.last_price = price
                                if self.on_price:
                                    await self.on_price(price)
            except Exception as e:
                logger.warning(f"[BINANCE] WS error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)
