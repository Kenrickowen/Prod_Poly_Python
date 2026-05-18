from __future__ import annotations

import unittest

from polymarket_python.bybit_client import parse_kline, parse_ticker_price
from polymarket_python.polymarket_public_client import (
    _parse_json_list,
    _parse_optional_float,
    current_btc_market_slug,
    parse_btc_market,
)


class PublicClientTests(unittest.TestCase):
    def test_bybit_ticker_parser_accepts_expected_topic(self) -> None:
        msg = {
            "topic": "tickers.BTCUSDT",
            "type": "snapshot",
            "ts": 123,
            "data": {"symbol": "BTCUSDT", "lastPrice": "76800.50"},
        }

        self.assertEqual(parse_ticker_price(msg, "BTCUSDT"), 76800.50)

    def test_bybit_ticker_parser_rejects_other_topic(self) -> None:
        msg = {"topic": "tickers.ETHUSDT", "data": {"lastPrice": "100"}}

        self.assertIsNone(parse_ticker_price(msg, "BTCUSDT"))

    def test_bybit_kline_parser(self) -> None:
        msg = {
            "topic": "kline.1.BTCUSDT",
            "data": [
                {
                    "start": 1779085200000,
                    "open": "76700",
                    "high": "76800",
                    "low": "76600",
                    "close": "76750",
                    "volume": "12.5",
                    "confirm": False,
                }
            ],
        }

        candle = parse_kline(msg, "BTCUSDT")

        self.assertIsNotNone(candle)
        self.assertEqual(candle.open_time_ms, 1779085200000)
        self.assertEqual(candle.close, 76750)

    def test_current_btc_market_slug_is_window_aligned(self) -> None:
        self.assertEqual(current_btc_market_slug(now_s=1779074734), "btc-updown-5m-1779074700")
        self.assertEqual(
            current_btc_market_slug(now_s=1779074734, offset_windows=1),
            "btc-updown-5m-1779075000",
        )

    def test_parse_json_list_handles_gamma_shapes(self) -> None:
        self.assertEqual(_parse_json_list('["up", "down"]'), ["up", "down"])
        self.assertEqual(_parse_json_list(["up", "down"]), ["up", "down"])
        self.assertEqual(_parse_json_list("not-json"), [])

    def test_parse_optional_float(self) -> None:
        self.assertEqual(_parse_optional_float("0.455"), 0.455)
        self.assertIsNone(_parse_optional_float(""))
        self.assertIsNone(_parse_optional_float("n/a"))

    def test_parse_btc_market_keeps_redemption_metadata(self) -> None:
        market = parse_btc_market(
            {
                "slug": "btc-updown-5m-1779074700",
                "question": "Bitcoin Up or Down",
                "conditionId": "0x" + "11" * 32,
                "negRisk": False,
                "closed": True,
                "acceptingOrders": False,
                "resolved": True,
                "clobTokenIds": '["123", "456"]',
                "outcomePrices": '["1", "0"]',
            }
        )

        self.assertIsNotNone(market)
        self.assertEqual(market.condition_id, "0x" + "11" * 32)
        self.assertEqual(market.token_id_up, "123")
        self.assertTrue(market.closed)
        self.assertTrue(market.resolved)


if __name__ == "__main__":
    unittest.main()
