#!/usr/bin/env python3
"""Connect to Bybit's public WebSocket and print BTCUSDT ticker prices."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.bybit_client import BybitClient
from polymarket_python.config import BYBIT_SYMBOL, BYBIT_WS_URL


async def main() -> None:
    parser = argparse.ArgumentParser(description="Stream Bybit BTCUSDT ticker prices.")
    parser.add_argument("--limit", type=int, default=5, help="price updates to print; 0 streams forever")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    seen = 0
    done = asyncio.Event()

    async def on_price(price: float) -> None:
        nonlocal seen
        seen += 1
        print(f"{BYBIT_SYMBOL} {price:.2f}", flush=True)
        if args.limit and seen >= args.limit:
            done.set()

    client = BybitClient(symbol=BYBIT_SYMBOL, ws_url=BYBIT_WS_URL, on_price=on_price)
    await client.start()

    try:
        await done.wait()
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
