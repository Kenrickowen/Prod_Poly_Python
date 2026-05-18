"""Read-only Polymarket market discovery and odds helpers."""
from __future__ import annotations

import json
import logging
import time
import asyncio
from dataclasses import dataclass

import httpx

from polymarket_python.config import GAMMA_HOST, POLYMARKET_HOST, WINDOW_MINUTES

logger = logging.getLogger(__name__)


@dataclass
class BtcMarket:
    slug: str
    question: str
    token_id_up: str
    token_id_down: str
    condition_id: str = ""
    neg_risk: bool = False
    closed: bool = False
    accepting_orders: bool = False
    resolved: bool = False
    gamma_up_odds: float | None = None
    gamma_down_odds: float | None = None


def current_btc_market_slug(now_s: int | None = None, offset_windows: int = 0) -> str:
    ts = int(now_s if now_s is not None else time.time())
    window_secs = WINDOW_MINUTES * 60
    window_ts = ((ts // window_secs) + offset_windows) * window_secs
    return f"btc-updown-5m-{window_ts}"


def _parse_json_list(value) -> list:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def _parse_optional_float(value) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


async def fetch_current_btc_market(client: httpx.AsyncClient | None = None) -> BtcMarket | None:
    """Fetch the currently active BTC 5m UP/DOWN market from Gamma."""
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=15)

    try:
        for offset in (0, -1, 1):
            slug = current_btc_market_slug(offset_windows=offset)
            resp = await http.get(f"{GAMMA_HOST}/markets", params={"slug": slug, "limit": 1})
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                logger.info("[POLY_PUBLIC] No Gamma market for slug=%s", slug)
                continue

            market = data[0]
            if market.get("closed") or not market.get("acceptingOrders"):
                logger.info("[POLY_PUBLIC] Market %s is closed or not accepting orders", slug)
                continue

            parsed = parse_btc_market(market, slug)
            if parsed is None:
                continue
            return parsed
        return None
    except Exception as e:
        logger.warning("[POLY_PUBLIC] Gamma fetch failed: %s", e)
        return None
    finally:
        if owns_client:
            await http.aclose()


def parse_btc_market(market: dict, fallback_slug: str = "") -> BtcMarket | None:
    """Parse the Gamma market shape used by BTC UP/DOWN markets."""
    token_ids = _parse_json_list(market.get("clobTokenIds"))
    slug = str(market.get("slug") or fallback_slug)
    if len(token_ids) < 2:
        logger.warning("[POLY_PUBLIC] Market %s has invalid token IDs: %s", slug, token_ids)
        return None

    prices = _parse_json_list(market.get("outcomePrices"))
    gamma_up = _parse_optional_float(prices[0]) if len(prices) >= 1 else None
    gamma_down = _parse_optional_float(prices[1]) if len(prices) >= 2 else None

    return BtcMarket(
        slug=slug,
        question=str(market.get("question") or ""),
        token_id_up=str(token_ids[0]),
        token_id_down=str(token_ids[1]),
        condition_id=str(market.get("conditionId") or ""),
        neg_risk=bool(market.get("negRisk")),
        closed=bool(market.get("closed")),
        accepting_orders=bool(market.get("acceptingOrders")),
        resolved=bool(market.get("resolved")),
        gamma_up_odds=gamma_up,
        gamma_down_odds=gamma_down,
    )


async def fetch_btc_market_by_slug(slug: str, client: httpx.AsyncClient | None = None) -> BtcMarket | None:
    """Fetch one BTC market by exact Gamma slug, including resolved/closed markets."""
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=15)

    try:
        resp = await http.get(f"{GAMMA_HOST}/markets", params={"slug": slug, "limit": 1})
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        return parse_btc_market(data[0], slug)
    except Exception as e:
        logger.warning("[POLY_PUBLIC] Gamma fetch failed for slug=%s: %s", slug, e)
        return None
    finally:
        if owns_client:
            await http.aclose()


async def fetch_midpoint(token_id: str, client: httpx.AsyncClient | None = None) -> float | None:
    """Fetch CLOB midpoint odds for a token ID."""
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=15)

    try:
        resp = await http.get(f"{POLYMARKET_HOST}/midpoint", params={"token_id": token_id})
        resp.raise_for_status()
        data = resp.json()
        return _parse_optional_float(data.get("mid") or data.get("mid_price"))
    except Exception as e:
        logger.warning("[POLY_PUBLIC] Midpoint fetch failed for %s: %s", token_id, e)
        return None
    finally:
        if owns_client:
            await http.aclose()


async def fetch_current_btc_odds() -> tuple[BtcMarket | None, float | None, float | None]:
    """Fetch active BTC market plus UP/DOWN CLOB midpoint odds."""
    async with httpx.AsyncClient(timeout=15) as client:
        market = await fetch_current_btc_market(client)
        if market is None:
            return None, None, None

        up_odds, down_odds = await asyncio.gather(
            fetch_midpoint(market.token_id_up, client),
            fetch_midpoint(market.token_id_down, client),
        )

        if up_odds is None:
            up_odds = market.gamma_up_odds
        if down_odds is None:
            down_odds = market.gamma_down_odds

        return market, up_odds, down_odds
