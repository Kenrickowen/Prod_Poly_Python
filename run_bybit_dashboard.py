#!/usr/bin/env python3
"""Run the dashboard with Bybit BTCUSDT WebSocket prices only."""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.bybit_client import BybitClient
from polymarket_python.config import BYBIT_SYMBOL
from polymarket_python.dashboard import Dashboard
from polymarket_python.models import AppState


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("BYBIT_DASHBOARD_PORT", os.getenv("DASHBOARD_PORT", "8081")))

    state = AppState(price_source="Bybit WebSocket")
    dashboard = Dashboard(state, host=host, port=port)

    async def on_price(price: float) -> None:
        dashboard.broadcast(dashboard._state_snapshot())

    bybit = BybitClient(state=state, symbol=BYBIT_SYMBOL, on_price=on_price)

    await bybit.start()
    logger = logging.getLogger(__name__)
    logger.info("[DASHBOARD] Bybit dashboard: http://%s:%s", host, port)

    try:
        await dashboard.start()
    finally:
        await bybit.stop()


if __name__ == "__main__":
    asyncio.run(main())
