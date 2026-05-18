#!/usr/bin/env python3
"""Fetch the active Polymarket BTC 5m market and print UP/DOWN odds."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.polymarket_public_client import fetch_current_btc_odds


async def main() -> None:
    market, up_odds, down_odds = await fetch_current_btc_odds()
    if market is None:
        print("No active BTC 5m market found")
        return

    print(f"Market: {market.question}")
    print(f"Slug: {market.slug}")
    print(f"Condition ID: {market.condition_id}")
    print(f"Neg risk: {market.neg_risk}")
    print(f"UP token: {market.token_id_up}")
    print(f"DOWN token: {market.token_id_down}")
    print(f"UP odds: {up_odds}")
    print(f"DOWN odds: {down_odds}")


if __name__ == "__main__":
    asyncio.run(main())
