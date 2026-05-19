"""Data models — Candle, WindowState, Signal, AppState."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CandleColor(Enum):
    GREEN = "green"
    RED = "red"
    DOJI = "doji"


class SignalDirection(Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class Candle:
    open: float
    close: float
    high: float
    low: float
    volume: float
    open_time_ms: int
    open_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    color: CandleColor = CandleColor.DOJI

    @classmethod
    def from_binance_kline(cls, k: dict) -> Candle:
        t = int(k["t"])
        o, h, l, c, v = float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])
        color = CandleColor.GREEN if c > o else CandleColor.RED if c < o else CandleColor.DOJI
        return cls(
            open=o, close=c, high=h, low=l, volume=v,
            open_time_ms=t,
            open_time=datetime.fromtimestamp(t / 1000, tz=timezone.utc),
            color=color,
        )

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class WindowState:
    ptb: float = 0.0
    ptb_source: str = ""
    ptb_binance: float = 0.0
    ptb_chainlink: float = 0.0
    signal = None
    window_start_ms: int = 0
    traded: bool = False
    signal_evaluated: bool = False
    first_in_window_candle_ms: int = 0

    def reset(self, window_start_ms: int) -> None:
        self.ptb = 0.0
        self.ptb_source = ""
        self.ptb_binance = 0.0
        self.ptb_chainlink = 0.0
        self.signal = None
        self.traded = False
        self.signal_evaluated = False
        self.window_start_ms = window_start_ms
        self.first_in_window_candle_ms = 0


@dataclass
class Signal:
    direction: SignalDirection
    reason: str
    trigger_candle: Optional[Candle] = None
    ptb_used: float = 0.0
    trend: str = ""
    atr: float = 0.0
    vol_sma: float = 0.0


@dataclass
class IndicatorState:
    atr: float = 0.0
    vol_sma: float = 0.0
    valid: bool = False


@dataclass
class Trade:
    timestamp_ms: int
    direction: SignalDirection
    token_id: str
    price: float  # odds at entry
    size: float   # spend amount
    condition_id: str = ""
    market_slug: str = ""
    order_id: str = ""
    signal_reason: str = ""
    signal_trend: str = ""
    signal_ptb: float = 0.0
    trigger_open: float = 0.0
    trigger_close: float = 0.0
    trigger_high: float = 0.0
    trigger_low: float = 0.0
    trigger_time_ms: int = 0
    token_id_up: str = ""
    token_id_down: str = ""
    neg_risk: bool = False
    pnl: float = 0.0
    settled: bool = False
    redemption_tx: str = ""
    redemption_error: str = ""
    redemption_checked_ms: int = 0


@dataclass
class AppState:
    klines: list[Candle] = field(default_factory=list)
    indicators: IndicatorState = field(default_factory=IndicatorState)
    window: WindowState = field(default_factory=WindowState)

    last_price: float = 0.0
    price_source: str = ""
    chainlink_price: Optional[float] = None
    poly_up_odds: Optional[float] = None
    poly_down_odds: Optional[float] = None
    poly_market_slug: str = ""
    poly_market_question: str = ""
    poly_market_condition_id: str = ""
    poly_market_neg_risk: bool = False

    wallet_address: str = ""
    wallet_pol_balance: Optional[float] = None
    wallet_usdc_balance: Optional[float] = None
    wallet_usdce_balance: Optional[float] = None
    wallet_pusd_balance: Optional[float] = None
    wallet_balance_error: str = ""
    last_wallet_balance_time_ms: int = 0

    trades_placed: int = 0
    initial_balance: float = 10_000.0
    current_balance: float = 10_000.0
    total_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    trade_history: list[Trade] = field(default_factory=list)

    last_kline_time_ms: int = 0
    last_ticker_time_ms: int = 0
    last_poly_odds_time_ms: int = 0
    last_signal_check_ms: int = 0
    last_signal_status: str = ""
    last_signal_reason: str = ""
    strategy_mode: str = "t3"  # "t3" | "legacy" | "current"

    def push_kline(self, candle: Candle) -> None:
        existing = next((i for i, c in enumerate(self.klines) if c.open_time_ms == candle.open_time_ms), -1)
        if existing >= 0:
            self.klines[existing] = candle
        else:
            self.klines.append(candle)
            if len(self.klines) > 120:
                self.klines.pop(0)

    def add_trade(self, trade: Trade) -> None:
        self.trades_placed += 1
        self.trade_history.insert(0, trade)
        if len(self.trade_history) > 50:
            self.trade_history.pop()
