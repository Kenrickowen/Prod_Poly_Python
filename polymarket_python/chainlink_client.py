"""Chainlink BTC/USD price feed via Data Engine REST API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Chainlink Data Engine API
CHAINLINK_API_URL = "https://data.chain.link/api/live-data-engine-stream-data"
CHAINLINK_BTC_FEED_ID = "0x00039d9e45394f473ab1f050a1b963e6b05351e52d71e507509ada0c95ed75b8"
CHAINLINK_ABI_INDEX = 0
CHAINLINK_QUERY_WINDOW = "1m"
CHAINLINK_ATTRIBUTE_NAME = "benchmark"
CHAINLINK_STALE_THRESHOLD_SECS = 60


def fetch_btc_price() -> float | None:
    """Fetch latest BTC/USD price from Chainlink Data Engine API."""
    import httpx

    url = (
        f"{CHAINLINK_API_URL}"
        f"?feedId={CHAINLINK_BTC_FEED_ID}"
        f"&abiIndex={CHAINLINK_ABI_INDEX}"
        f"&queryWindow={CHAINLINK_QUERY_WINDOW}"
        f"&attributeName={CHAINLINK_ATTRIBUTE_NAME}"
    )

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()

        nodes = data.get("data", {}).get("allStreamValuesGenerics", {}).get("nodes", [])
        if not nodes:
            logger.warning("[CHAINLINK] No nodes in response")
            return None

        node = nodes[0]
        price_str = node.get("valueNumeric")
        valid_after_ts = node.get("validAfterTs", "")

        # Check stale price
        if valid_after_ts:
            try:
                valid_after = datetime.fromisoformat(valid_after_ts.replace("Z", "+00:00"))
                age_secs = (datetime.now(timezone.utc) - valid_after).total_seconds()
                if age_secs > CHAINLINK_STALE_THRESHOLD_SECS:
                    logger.warning(f"[CHAINLINK] Price is stale: {age_secs:.0f}s old")
            except Exception:
                pass

        if price_str:
            price = float(price_str)
            logger.debug(f"[CHAINLINK] BTC/USD = ${price:,.2f}")
            return price

        return None

    except Exception as e:
        logger.warning(f"[CHAINLINK] Failed to fetch price: {e}")
        return None
