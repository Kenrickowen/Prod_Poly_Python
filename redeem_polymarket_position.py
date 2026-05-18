#!/usr/bin/env python3
"""Check or redeem a resolved Polymarket BTC 5m position by market slug."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv(Path(__file__).parent / ".env")

from polymarket_python.polymarket_public_client import current_btc_market_slug, fetch_btc_market_by_slug
from polymarket_python.redemption import PolymarketRedeemer


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="", help="BTC 5m Gamma slug, e.g. btc-updown-5m-1779082500")
    parser.add_argument("--execute", action="store_true", help="Submit the redemption transaction")
    parser.add_argument("--wait", action="store_true", help="Wait for the redemption transaction receipt")
    args = parser.parse_args()

    slug = args.slug or current_btc_market_slug(offset_windows=-1)
    market = await fetch_btc_market_by_slug(slug)
    if market is None:
        print(f"No market found for slug: {slug}")
        return 1

    redeemer = PolymarketRedeemer()
    up_balance, down_balance = redeemer.get_balances(market.token_id_up, market.token_id_down)
    resolved = redeemer.is_resolved(market.condition_id)

    print(f"Market: {market.question}")
    print(f"Slug: {market.slug}")
    print(f"Condition ID: {market.condition_id}")
    print(f"Resolved on CTF: {resolved}")
    print(f"UP raw balance: {up_balance}")
    print(f"DOWN raw balance: {down_balance}")

    if not args.execute:
        print("Dry run only. Add --execute to submit redemption when resolved.")
        return 0

    result = redeemer.redeem(
        condition_id=market.condition_id,
        token_id_up=market.token_id_up,
        token_id_down=market.token_id_down,
        neg_risk=market.neg_risk,
        wait_for_receipt=args.wait,
    )
    if result.redeemed:
        print(f"Redemption submitted: {result.tx_hash}")
        return 0

    print(f"Nothing redeemed: {result.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
