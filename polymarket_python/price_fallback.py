"""Fallback BTC price sources when Binance is geo-blocked."""
import logging

from polymarket_python.config import GAMMA_HOST

logger = logging.getLogger(__name__)


async def fetch_btc_price_coingecko() -> float | None:
    """Fetch BTC/USD price from CoinGecko public API (no auth needed)."""
    import httpx

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": "usd"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            price = data.get("bitcoin", {}).get("usd")
            if price:
                logger.info(f"[COINGECKO] BTC/USD = ${price:,.2f}")
                return float(price)
    except Exception as e:
        logger.warning(f"[COINGECKO] Failed to fetch BTC price: {e}")
        return None


async def fetch_btc_price_binance_rest() -> float | None:
    """Fetch BTC/USDT price from Binance REST API (no auth needed)."""
    import httpx

    url = "https://api.binance.com/api/v3/price"
    params = {"symbol": "BTCUSDT"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            price = data.get("price")
            if price:
                return float(price)
    except Exception as e:
        logger.debug(f"[BINANCE_REST] Failed: {e}")
        return None


async def fetch_btc_price_from_poly_market() -> float | None:
    """
    Derive BTC price from Polymarket BTC 5m market odds.
    If UP odds are p, DOWN odds are (1-p), and market is well-structured,
    the geometric mean gives an approximation of the implied BTC price.
    This is approximate but works as a fallback.
    """
    import httpx
    import json

    try:
        now_s = int(__import__("time").time())
        window_ts = (now_s // 300) * 300
        slug = f"btc-updown-5m-{window_ts}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{GAMMA_HOST}/markets", params={"slug": slug, "limit": 1})
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                return None

            m = data[0]
            prices_raw = m.get("outcomePrices", "[]")
            prices = json.loads(prices_raw) if isinstance(prices_raw, str) else prices_raw
            if len(prices) >= 2:
                up_odds = float(prices[0])
                down_odds = float(prices[1])
                # Use the mid price as indicator, not exact BTC price
                mid = (up_odds + down_odds) / 2
                return mid if mid > 0 else None
    except Exception as e:
        logger.debug(f"[POLY_MARKET] Failed to derive BTC price: {e}")
        return None