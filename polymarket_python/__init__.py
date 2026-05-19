# Polymarket BTC 5m Breakout Trading Bot
from polymarket_python.models import Candle, WindowState, Signal, AppState, CandleColor, SignalDirection
from polymarket_python.config import *
from polymarket_python.strategy import evaluate_signal
from polymarket_python.scheduler import calculate_window_start, window_elapsed_ms
from polymarket_python.indicators import update_indicators, compute_atr, compute_vol_sma
from polymarket_python.state import reset_window, capture_ptb_from_binance
from polymarket_python.guardrails import should_trade
from polymarket_python.binance_client import BinanceClient
from polymarket_python.bybit_client import BybitClient

try:
    from polymarket_python.trader import Trader
    from polymarket_python.polymarket_client import PolymarketClient
except ModuleNotFoundError as exc:
    if exc.name not in {"py_clob_client", "py_clob_client_v2", "py_order_utils"}:
        raise
    Trader = None
    PolymarketClient = None
