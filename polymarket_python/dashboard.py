"""FastAPI dashboard with WebSocket streaming of real-time state."""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import FileResponse, HTMLResponse, Response
import uvicorn

from polymarket_python.config import TRADE_HISTORY_CSV
from polymarket_python.models import AppState, Trade
from polymarket_python.runtime_config import save_position_size

logger = logging.getLogger(__name__)


class Dashboard:
    """
    FastAPI HTTP server + WebSocket streaming.
    Serves a simple HTML dashboard and broadcasts state updates via WebSocket.
    """

    def __init__(self, state: AppState, host: str = "0.0.0.0", port: int = 8080):
        self.state = state
        self.host = host
        self.port = port
        self.app = FastAPI(title="Polymarket BTC Bot")
        self._ws_clients: list[WebSocket] = []
        self._runner: uvicorn.Server | None = None

        self._setup_routes()

    def _setup_routes(self) -> None:
        @self.app.get("/")
        async def index() -> HTMLResponse:
            return HTMLResponse(self._html_dashboard())

        @self.app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket) -> None:
            await ws.accept()
            self._ws_clients.append(ws)
            try:
                await ws.send_json(self._state_snapshot())
                while True:
                    await asyncio.sleep(1)
                    try:
                        await ws.send_json(self._state_snapshot())
                    except Exception:
                        break
            except WebSocketDisconnect:
                pass
            finally:
                if ws in self._ws_clients:
                    self._ws_clients.remove(ws)

        @self.app.post("/config/strategy_mode")
        async def set_strategy_mode(body: bytes = Body(..., media_type="text/plain")) -> dict[str, str]:
            mode = body.decode("utf-8").strip()
            if mode not in ("legacy", "t3"):
                return {"error": "Invalid mode. Use 't3' or 'legacy'."}
            self.state.strategy_mode = mode
            return {"strategy_mode": mode}

        @self.app.get("/config/strategy_mode")
        async def get_strategy_mode() -> dict[str, str]:
            return {"strategy_mode": self.state.strategy_mode}

        @self.app.post("/config/position_size")
        async def set_position_size(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
            mode = str(body.get("mode") or "").strip().lower()
            if mode not in ("fixed", "percent"):
                return {"error": "Invalid mode. Use 'fixed' or 'percent'."}
            try:
                fixed_usd = float(body.get("fixed_usd", self.state.position_fixed_usd))
                equity_percent = float(body.get("equity_percent", self.state.position_equity_percent))
            except (TypeError, ValueError):
                return {"error": "Position size values must be numbers."}
            if fixed_usd < 0 or equity_percent < 0:
                return {"error": "Position size values cannot be negative."}
            if mode == "fixed" and fixed_usd <= 0:
                return {"error": "Fixed dollar size must be greater than 0."}
            if mode == "percent" and equity_percent <= 0:
                return {"error": "Equity percentage must be greater than 0."}

            self.state.position_size_mode = mode
            self.state.position_fixed_usd = fixed_usd
            self.state.position_equity_percent = equity_percent
            save_position_size(self.state)
            return self._position_size_config()

        @self.app.get("/config/position_size")
        async def get_position_size() -> dict[str, Any]:
            return self._position_size_config()

        @self.app.get("/state")
        async def get_state() -> dict[str, Any]:
            return self._state_snapshot()

        @self.app.get("/trades.csv")
        async def get_trades_csv():
            path = Path(TRADE_HISTORY_CSV)
            if not path.is_absolute():
                path = Path(__file__).resolve().parent.parent / path
            if not path.exists():
                return Response(
                    "timestamp_ms,direction,market_slug,condition_id,token_id,price,size,pnl,settled,redemption_tx\n",
                    media_type="text/csv",
                )
            return FileResponse(path, media_type="text/csv", filename="trade_history.csv")

    def _state_snapshot(self) -> dict[str, Any]:
        """Serialize current app state for JSON response / WebSocket."""
        window = self.state.window
        indicators = self.state.indicators
        trade_pnls = {id(t): self._trade_pnl(t) for t in self.state.trade_history}
        total_pnl = self._total_pnl(trade_pnls)

        signal_value = None
        if window.signal is not None:
            signal_value = window.signal.direction.value if hasattr(window.signal, 'direction') else str(window.signal)

        # Serialize trade history
        trade_history = []
        for t in self.state.trade_history:
            trade_history.append({
                "time": t.timestamp_ms,
                "direction": t.direction.value,
                "token_id": t.token_id,
                "price": t.price,
                "size": t.size,
                "pnl": trade_pnls[id(t)],
                "settled": t.settled,
                "market_slug": t.market_slug,
                "condition_id": t.condition_id,
                "token_id_up": t.token_id_up,
                "token_id_down": t.token_id_down,
                "neg_risk": t.neg_risk,
                "redemption_tx": t.redemption_tx,
                "redemption_error": t.redemption_error,
                "redemption_checked_ms": t.redemption_checked_ms,
                "order_id": t.order_id,
                "signal_reason": t.signal_reason,
                "signal_trend": t.signal_trend,
                "signal_ptb": t.signal_ptb,
                "trigger_time_ms": t.trigger_time_ms,
            })

        klines = []
        for c in self.state.klines[-80:]:
            klines.append({
                "time": c.open_time_ms,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "color": c.color.value,
            })

        return {
            "last_price": self.state.last_price,
            "price_source": self.state.price_source,
            "poly_up_odds": self.state.poly_up_odds,
            "poly_down_odds": self.state.poly_down_odds,
            "poly_market_slug": self.state.poly_market_slug,
            "poly_market_question": self.state.poly_market_question,
            "poly_market_condition_id": self.state.poly_market_condition_id,
            "poly_market_neg_risk": self.state.poly_market_neg_risk,
            "wallet": {
                "address": self.state.wallet_address,
                "pol": self.state.wallet_pol_balance,
                "usdc": self.state.wallet_usdc_balance,
                "usdce": self.state.wallet_usdce_balance,
                "pusd": self.state.wallet_pusd_balance,
                "error": self.state.wallet_balance_error,
                "last_update_ms": self.state.last_wallet_balance_time_ms,
            },
            "window": {
                "start_ms": window.window_start_ms,
                "ptb": window.ptb,
                "ptb_source": window.ptb_source,
                "ptb_binance": window.ptb_binance,
                "signal": signal_value,
                "traded": window.traded,
                "signal_evaluated": window.signal_evaluated,
                "first_in_window_candle_ms": window.first_in_window_candle_ms,
            },
            "signal_status": {
                "last_check_ms": self.state.last_signal_check_ms,
                "status": self.state.last_signal_status,
                "reason": self.state.last_signal_reason,
            },
            "indicators": {
                "atr": indicators.atr,
                "vol_sma": indicators.vol_sma,
                "valid": indicators.valid,
            },
            "metrics": {
                "trades_placed": self.state.trades_placed,
                "win_count": self.state.win_count,
                "loss_count": self.state.loss_count,
                "total_pnl": total_pnl,
                "current_balance": self.state.current_balance,
                "initial_balance": self.state.initial_balance,
            },
            "klines_count": len(self.state.klines),
            "last_kline_time_ms": self.state.last_kline_time_ms,
            "last_ticker_time_ms": self.state.last_ticker_time_ms,
            "last_poly_odds_time_ms": self.state.last_poly_odds_time_ms,
            "strategy_mode": self.state.strategy_mode,
            "position_size": self._position_size_config(),
            "klines": klines,
            "trade_history": trade_history,
        }

    def _position_size_config(self) -> dict[str, Any]:
        return {
            "mode": self.state.position_size_mode,
            "fixed_usd": self.state.position_fixed_usd,
            "equity_percent": self.state.position_equity_percent,
        }

    def _trade_current_odds(self, trade: Trade) -> float | None:
        if trade.market_slug and trade.market_slug != self.state.poly_market_slug:
            return None
        if trade.token_id and trade.token_id == trade.token_id_up:
            return self.state.poly_up_odds if trade.token_id_up else None
        if trade.token_id and trade.token_id == trade.token_id_down:
            return self.state.poly_down_odds if trade.token_id_down else None
        if trade.direction.value == "UP":
            return self.state.poly_up_odds
        if trade.direction.value == "DOWN":
            return self.state.poly_down_odds
        return None

    def _open_trade_value(self, trade: Trade) -> float:
        if trade.settled or trade.redemption_tx:
            return 0.0
        if trade.price <= 0:
            return trade.size
        odds = self._trade_current_odds(trade)
        if odds is None:
            return trade.size
        return (trade.size / trade.price) * odds

    def _trade_pnl(self, trade: Trade) -> float:
        if trade.settled or trade.redemption_tx:
            return trade.pnl
        return self._open_trade_value(trade) - trade.size

    def _total_pnl(self, trade_pnls: dict[int, float]) -> float:
        if self.state.initial_balance > 0 and self.state.wallet_pusd_balance is not None:
            open_value = sum(self._open_trade_value(t) for t in self.state.trade_history)
            return (self.state.current_balance + open_value) - self.state.initial_balance
        if trade_pnls:
            return sum(trade_pnls.values())
        return self.state.total_pnl

    def _html_dashboard(self) -> str:
        """Simple dark-themed HTML dashboard with real-time WebSocket updates."""
        return """<!DOCTYPE html>
<html>
<head>
  <title>Polymarket BTC Bot</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #e6edf3; padding: 20px; min-height: 100vh; }
    h1 { color: #58a6ff; font-size: 22px; margin-bottom: 4px; }
    .subtitle { color: #8b949e; font-size: 13px; margin-bottom: 20px; }
    .topbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; max-width: 1400px; margin: 0 0 14px 0; }
    .clock { min-width: 150px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 8px 10px; }
    .clock .label { color: #8b949e; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px; }
    .clock .time { color: #e6edf3; font-size: 15px; font-family: monospace; font-weight: 600; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; max-width: 1400px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
    .card h3 { color: #8b949e; margin: 0 0 12px 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
    .card .big-val { font-size: 26px; font-weight: 600; color: #58a6ff; }
    .card .small-val { font-size: 13px; color: #8b949e; margin-top: 4px; }
    .mono { font-family: monospace; }
    .up { color: #3fb950; }
    .down { color: #f85149; }
    .neutral { color: #d29922; }
    table { width: 100%; border-collapse: collapse; }
    td { padding: 5px 0; border-bottom: 1px solid #21262d; font-size: 13px; }
    td:first-child { color: #8b949e; width: 45%; }
    td:last-child { color: #e6edf3; font-family: monospace; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .badge-up { background: #1f4d2a; color: #3fb950; }
    .badge-down { background: #4d1f1f; color: #f85149; }
    .badge-neutral { background: #2d200a; color: #d29922; }
    #ws-status { font-size: 12px; color: #8b949e; margin-bottom: 16px; }
    #ws-status .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #8b949e; margin-right: 6px; }
    #ws-status.connected .dot { background: #3fb950; }
    #ws-status.disconnected .dot { background: #f85149; }
    .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #8b949e; margin: 16px 0 8px 0; }
    .pnl { font-size: 20px; font-weight: 600; }
    .pnl.positive { color: #3fb950; }
    .pnl.negative { color: #f85149; }
    .row { display: flex; justify-content: space-between; align-items: center; }
    .tag { font-size: 10px; padding: 1px 5px; border-radius: 3px; background: #30363d; color: #8b949e; }
    .chart-wrap { max-width: 1400px; height: 280px; padding: 0; overflow: hidden; }
    #kline-chart { width: 100%; height: 240px; display: block; }
    .table-wrap { max-width: 1400px; overflow-x: auto; }
    th { white-space: nowrap; }
    .strategy-btn { background: #238636; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; }
    .strategy-btn:hover { background: #2ea043; }
    .strategy-btn.legacy { background: #da3633; }
    .strategy-btn.legacy:hover { background: #f85149; }
    .strategy-indicator { display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 700; background: #238636; color: #fff; }
    .strategy-indicator.legacy { background: #da3633; }
    .control-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: end; }
    .control-field label { display: block; color: #8b949e; font-size: 11px; margin-bottom: 4px; }
    .control-field input, .control-field select { width: 100%; background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 7px 9px; font-size: 13px; }
    .control-btn { background: #238636; color: #fff; border: none; border-radius: 6px; padding: 8px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .control-btn:hover { background: #2ea043; }
    .control-status { min-height: 16px; color: #8b949e; font-size: 12px; margin-top: 8px; }
  </style>
</head>
<body>
  <h1>Polymarket BTC 5m Breakout</h1>
  <p class="subtitle">Strategy B - Binance BTC -> Polymarket CLOB</p>
  <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center;">
    <span id="strategy-indicator" class="strategy-indicator">CURRENT</span>
    <select id="strategy-select" onchange="setStrategy(this.value)" style="background: #161b22; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer;">
      <option value="t3">T3 (Candle 3)</option>
      <option value="legacy">Legacy</option>
    </select>
  </div>
  <div class="topbar">
    <div class="clock">
      <div class="label">Project Time GMT+7</div>
      <div class="time" id="clock-gmt7">--</div>
    </div>
    <div class="clock">
      <div class="label">UTC</div>
      <div class="time" id="clock-utc">--</div>
    </div>
    <div class="clock">
      <div class="label">New York</div>
      <div class="time" id="clock-ny">--</div>
    </div>
    <div class="clock">
      <div class="label">London</div>
      <div class="time" id="clock-london">--</div>
    </div>
  </div>
  <div id="ws-status"><span class="dot"></span>Connecting...</div>

  <div class="grid">
    <!-- Row 1: Price feeds -->
    <div class="card">
      <h3>BTC Price</h3>
      <div class="big-val" id="last-price">--</div>
      <div class="small-val" id="last-price-time">--</div>
    </div>
    <div class="card">
      <h3>Wallet Balances</h3>
      <table>
        <tr><td>Gas POL</td><td id="wallet-pol">--</td></tr>
        <tr><td>USDC</td><td id="wallet-usdc">--</td></tr>
        <tr><td>USDC.e</td><td id="wallet-usdce">--</td></tr>
        <tr><td>pUSD</td><td id="wallet-pusd">--</td></tr>
        <tr><td>Updated</td><td id="wallet-updated">--</td></tr>
      </table>
      <div class="small-val mono" id="wallet-address">--</div>
    </div>

    <!-- Row 2: Polymarket odds -->
    <div class="card">
      <h3>Poly UP Odds</h3>
      <div class="big-val up" id="poly-up">--</div>
      <div class="small-val" id="poly-up-label">Awaiting market...</div>
    </div>
    <div class="card">
      <h3>Poly DOWN Odds</h3>
      <div class="big-val down" id="poly-down">--</div>
      <div class="small-val" id="poly-down-label">Awaiting market...</div>
    </div>

    <!-- Row 3: Window state -->
    <div class="card">
      <h3>Current Window</h3>
      <table>
        <tr><td>Window Start</td><td id="w-start">--</td></tr>
        <tr><td>PTB Price</td><td id="w-ptb">--</td></tr>
        <tr><td>PTB Source</td><td id="w-ptb-src">--</td></tr>
        <tr><td>Signal</td><td id="w-signal">--</td></tr>
        <tr><td>Traded</td><td id="w-traded">--</td></tr>
        <tr><td>Window Progress</td><td id="w-progress">--</td></tr>
      </table>
    </div>
    <div class="card">
      <h3>Indicators</h3>
      <table>
        <tr><td>ATR (5)</td><td id="ind-atr">--</td></tr>
        <tr><td>Vol SMA (5)</td><td id="ind-vol">--</td></tr>
        <tr><td>Indicators Valid</td><td id="ind-valid">--</td></tr>
        <tr><td>Klines Loaded</td><td id="klines-count">--</td></tr>
        <tr><td>First In-Window Candle</td><td id="w-first-candle">--</td></tr>
      </table>
    </div>

    <!-- Row 4: Metrics -->
    <div class="card">
      <h3>PnL</h3>
      <div class="pnl" id="total-pnl">--</div>
      <div class="small-val" id="balance">Balance: --</div>
    </div>
    <div class="card">
      <h3>Trading Stats</h3>
      <table>
        <tr><td>Trades Placed</td><td id="t-placed">0</td></tr>
        <tr><td>Wins</td><td class="up" id="t-wins">0</td></tr>
        <tr><td>Losses</td><td class="down" id="t-losses">0</td></tr>
        <tr><td>Last Signal Check</td><td id="signal-check">--</td></tr>
        <tr><td>Signal Status</td><td id="signal-status">--</td></tr>
      </table>
    </div>
    <div class="card">
      <h3>Position Size</h3>
      <div class="control-grid">
        <div class="control-field">
          <label for="position-mode">Mode</label>
          <select id="position-mode">
            <option value="fixed">Fixed $</option>
            <option value="percent">% Equity</option>
          </select>
        </div>
        <div class="control-field">
          <label for="position-fixed">Fixed USD</label>
          <input id="position-fixed" type="number" min="0" step="0.01">
        </div>
        <div class="control-field">
          <label for="position-percent">Equity %</label>
          <input id="position-percent" type="number" min="0" step="0.1">
        </div>
        <button class="control-btn" type="button" onclick="setPositionSize()">Save</button>
      </div>
      <div class="control-status" id="position-status">--</div>
    </div>
  </div>

  <div class="section-title">BTC 1m Klines</div>
  <div class="card chart-wrap">
    <canvas id="kline-chart"></canvas>
    <div class="small-val" id="kline-caption" style="padding: 0 16px 12px 16px;">Awaiting candles...</div>
  </div>

  <div class="section-title">Trade History</div>
  <div class="card table-wrap">
    <div class="small-val" style="margin-bottom: 8px;"><a href="/trades.csv" style="color:#58a6ff;">Download CSV</a></div>
    <table id="trade-table" style="font-size: 12px;">
      <thead>
        <tr style="border-bottom: 1px solid #30363d;">
          <th style="text-align:left; padding: 4px 0; color:#8b949e; font-weight: normal;">Time</th>
          <th style="text-align:left; padding: 4px 8px; color:#8b949e; font-weight: normal;">Dir</th>
          <th style="text-align:left; padding: 4px 8px; color:#8b949e; font-weight: normal;">Market</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">Entry Odds</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">Size</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">PnL</th>
          <th style="text-align:center; padding: 4px 8px; color:#8b949e; font-weight: normal;">Redeem</th>
          <th style="text-align:left; padding: 4px 8px; color:#8b949e; font-weight: normal;">Signal</th>
        </tr>
      </thead>
      <tbody id="trade-body">
        <tr><td colspan="8" style="color:#8b949e; padding: 8px 0;">No trades yet</td></tr>
      </tbody>
    </table>
  </div>

  <script>
    function formatTime(ts) {
      if (!ts) return '--';
      return new Date(ts).toLocaleString('en-GB', {
        timeZone: 'Asia/Jakarta',
        hour12: false,
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }) + ' GMT+7';
    }
    function formatClock(zone, includeDate = false) {
      const opts = {
        timeZone: zone,
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      };
      if (includeDate) {
        opts.month = 'short';
        opts.day = '2-digit';
      }
      return new Date().toLocaleString('en-GB', opts);
    }
    function tickClocks() {
      document.getElementById('clock-gmt7').textContent = formatClock('Asia/Jakarta', true);
      document.getElementById('clock-utc').textContent = formatClock('UTC', true);
      document.getElementById('clock-ny').textContent = formatClock('America/New_York');
      document.getElementById('clock-london').textContent = formatClock('Europe/London');
    }
    function formatPrice(v) {
      if (!v) return '--';
      return '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    function formatOdds(v) {
      if (!v) return '--';
      return v.toFixed(4);
    }
    function formatToken(v, digits = 4) {
      if (v === null || v === undefined) return '--';
      return Number(v).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: digits});
    }
    function shortAddress(v) {
      if (!v) return '--';
      return v.slice(0, 6) + '...' + v.slice(-4);
    }
    function drawKlines(klines) {
      const canvas = document.getElementById('kline-chart');
      const caption = document.getElementById('kline-caption');
      const ctx = canvas.getContext('2d');
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const width = rect.width;
      const height = rect.height;
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#0d1117';
      ctx.fillRect(0, 0, width, height);

      const data = (klines || []).slice(-60);
      if (!data.length) {
        caption.textContent = 'Awaiting candles...';
        return;
      }

      const pad = { left: 54, right: 16, top: 14, bottom: 24 };
      const prices = data.flatMap(k => [k.high, k.low]).filter(v => Number.isFinite(v));
      const min = Math.min(...prices);
      const max = Math.max(...prices);
      const span = Math.max(max - min, 1);
      const plotW = width - pad.left - pad.right;
      const plotH = height - pad.top - pad.bottom;
      const xStep = plotW / Math.max(data.length, 1);
      const candleW = Math.max(3, Math.min(10, xStep * 0.55));
      const y = (price) => pad.top + ((max - price) / span) * plotH;

      ctx.strokeStyle = '#30363d';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i <= 4; i++) {
        const yy = pad.top + (plotH / 4) * i;
        ctx.moveTo(pad.left, yy);
        ctx.lineTo(width - pad.right, yy);
      }
      ctx.stroke();

      ctx.fillStyle = '#8b949e';
      ctx.font = '11px monospace';
      ctx.textAlign = 'right';
      for (let i = 0; i <= 4; i++) {
        const price = max - (span / 4) * i;
        ctx.fillText(price.toFixed(1), pad.left - 8, pad.top + (plotH / 4) * i + 4);
      }

      data.forEach((k, i) => {
        const x = pad.left + i * xStep + xStep / 2;
        const up = k.close >= k.open;
        const color = up ? '#3fb950' : '#f85149';
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, y(k.high));
        ctx.lineTo(x, y(k.low));
        ctx.stroke();
        const top = y(Math.max(k.open, k.close));
        const bottom = y(Math.min(k.open, k.close));
        ctx.fillRect(x - candleW / 2, top, candleW, Math.max(bottom - top, 1));
      });

      const last = data[data.length - 1];
      caption.textContent = `${data.length} candles · last ${formatTime(last.time)} · O ${last.open.toFixed(1)} H ${last.high.toFixed(1)} L ${last.low.toFixed(1)} C ${last.close.toFixed(1)}`;
    }

    async function setStrategy(mode) {
      try {
        const resp = await fetch('/config/strategy_mode', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain' },
          body: mode,
        });
        const json = await resp.json();
        if (json.error) {
          alert('Error: ' + json.error);
        }
      } catch (e) {
        alert('Failed to switch strategy: ' + e);
      }
    }

    async function setPositionSize() {
      const mode = document.getElementById('position-mode').value;
      const fixed = Number(document.getElementById('position-fixed').value);
      const percent = Number(document.getElementById('position-percent').value);
      const status = document.getElementById('position-status');
      status.textContent = 'Saving...';
      try {
        const resp = await fetch('/config/position_size', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode, fixed_usd: fixed, equity_percent: percent }),
        });
        const json = await resp.json();
        if (json.error) {
          status.textContent = json.error;
          status.className = 'control-status down';
          return;
        }
        updatePositionSizeUI(json);
        status.className = 'control-status up';
      } catch (e) {
        status.textContent = 'Failed to save position size';
        status.className = 'control-status down';
      }
    }

    function updatePositionSizeUI(config) {
      if (!config) return;
      const activeId = document.activeElement ? document.activeElement.id : '';
      if (['position-mode', 'position-fixed', 'position-percent'].includes(activeId)) return;
      const modeEl = document.getElementById('position-mode');
      const fixedEl = document.getElementById('position-fixed');
      const percentEl = document.getElementById('position-percent');
      const status = document.getElementById('position-status');
      modeEl.value = config.mode || 'fixed';
      fixedEl.value = Number(config.fixed_usd || 0).toFixed(2);
      percentEl.value = Number(config.equity_percent || 0).toFixed(2);
      if (modeEl.value === 'percent') {
        status.textContent = `Next trade: ${Number(config.equity_percent || 0).toFixed(2)}% of equity`;
      } else {
        status.textContent = `Next trade: $${Number(config.fixed_usd || 0).toFixed(2)}`;
      }
      status.className = 'control-status';
    }

    function updateStrategyUI(mode) {
      const indicator = document.getElementById('strategy-indicator');
      const select = document.getElementById('strategy-select');
      if (mode === 'legacy') {
        indicator.textContent = 'LEGACY';
        indicator.className = 'strategy-indicator legacy';
        indicator.style.background = '#da3633';
        if (select) select.value = 'legacy';
      } else if (mode === 't3') {
        indicator.textContent = 'T3';
        indicator.className = 'strategy-indicator';
        indicator.style.background = '#238636';
        if (select) select.value = 't3';
      } else {
        // 'current' — not shown in dropdown but supported in code
        indicator.textContent = 'CURRENT';
        indicator.className = 'strategy-indicator';
        indicator.style.background = '#8b949e';
      }
    }

    const ws = new WebSocket(`ws://${location.host}/ws`);
    const statusEl = document.getElementById('ws-status');
    tickClocks();
    setInterval(tickClocks, 1000);

    ws.onopen = () => { statusEl.className = 'connected'; statusEl.innerHTML = '<span class="dot"></span>Connected — live data'; };
    ws.onclose = () => { statusEl.className = 'disconnected'; statusEl.innerHTML = '<span class="dot"></span>Disconnected — reconnecting...'; setTimeout(() => location.reload(), 3000); };
    ws.onerror = () => { ws.close(); };

    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);

      // Strategy mode indicator
      updateStrategyUI(d.strategy_mode || 'current');
      updatePositionSizeUI(d.position_size);

      // Price feeds
      document.getElementById('last-price').textContent = d.last_price ? d.last_price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--';
      const priceTs = d.last_ticker_time_ms || d.last_kline_time_ms;
      const priceSource = d.price_source || 'Market feed';
      document.getElementById('last-price-time').textContent = priceTs ? `${priceSource} · ${formatTime(priceTs)}` : priceSource;
      // Wallet balances
      const wallet = d.wallet || {};
      document.getElementById('wallet-pol').textContent = wallet.error ? '--' : formatToken(wallet.pol, 6);
      document.getElementById('wallet-usdc').textContent = wallet.error ? '--' : formatToken(wallet.usdc, 2);
      document.getElementById('wallet-usdce').textContent = wallet.error ? '--' : formatToken(wallet.usdce, 2);
      document.getElementById('wallet-pusd').textContent = wallet.error ? '--' : formatToken(wallet.pusd, 2);
      document.getElementById('wallet-updated').textContent = wallet.error ? wallet.error : formatTime(wallet.last_update_ms);
      document.getElementById('wallet-address').textContent = shortAddress(wallet.address);

      // Odds
      document.getElementById('poly-up').textContent = d.poly_up_odds ? formatOdds(d.poly_up_odds) : '--';
      document.getElementById('poly-down').textContent = d.poly_down_odds ? formatOdds(d.poly_down_odds) : '--';
      document.getElementById('poly-up-label').textContent = d.last_poly_odds_time_ms ? `CLOB midpoint · ${formatTime(d.last_poly_odds_time_ms)}` : (d.poly_market_slug || 'Awaiting market...');
      document.getElementById('poly-down-label').textContent = d.poly_market_slug || 'Awaiting market...';

      // Window
      const w = d.window || {};
      document.getElementById('w-start').textContent = w.start_ms ? formatTime(w.start_ms) : '--';
      document.getElementById('w-ptb').textContent = w.ptb ? w.ptb.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--';
      document.getElementById('w-ptb-src').textContent = w.ptb_source || '--';

      const sig = w.signal;
      if (sig) {
        const cls = sig === 'UP' ? 'badge-up' : 'badge-down';
        document.getElementById('w-signal').innerHTML = `<span class="badge ${cls}">${sig}</span>`;
      } else {
        document.getElementById('w-signal').textContent = w.signal_evaluated ? 'Evaluated' : 'Pending';
      }

      document.getElementById('w-traded').textContent = w.traded ? 'YES' : 'No';
      document.getElementById('w-first-candle').textContent = w.first_in_window_candle_ms ? formatTime(w.first_in_window_candle_ms) : '--';

      // Progress bar for window (5min = 300000ms)
      if (w.start_ms && d.last_kline_time_ms) {
        const elapsed = d.last_kline_time_ms - w.start_ms;
        const pct = Math.min(100, (elapsed / 300000) * 100).toFixed(0);
        document.getElementById('w-progress').textContent = pct + '% (' + (elapsed/1000).toFixed(0) + 's / 300s)';
      } else {
        document.getElementById('w-progress').textContent = '--';
      }

      // Indicators
      const ind = d.indicators || {};
      document.getElementById('ind-atr').textContent = ind.atr ? ind.atr.toFixed(2) : '--';
      document.getElementById('ind-vol').textContent = ind.vol_sma ? ind.vol_sma.toFixed(2) : '--';
      document.getElementById('ind-valid').textContent = ind.valid ? 'YES' : 'NO';
      document.getElementById('klines-count').textContent = d.klines_count || 0;

      // Metrics
      const m = d.metrics || {};
      const pnlEl = document.getElementById('total-pnl');
      if (m.total_pnl !== undefined && m.total_pnl !== null) {
        pnlEl.textContent = (m.total_pnl >= 0 ? '+$' : '-$') + Math.abs(m.total_pnl).toFixed(2);
        pnlEl.className = 'pnl ' + (m.total_pnl >= 0 ? 'positive' : 'negative');
      } else {
        pnlEl.textContent = '--';
        pnlEl.className = 'pnl';
      }
      document.getElementById('balance').textContent = 'Balance: $' + (m.current_balance || 0).toFixed(2);
      document.getElementById('t-placed').textContent = m.trades_placed || 0;
      document.getElementById('t-wins').textContent = m.win_count || 0;
      document.getElementById('t-losses').textContent = m.loss_count || 0;
      const signalStatus = d.signal_status || {};
      document.getElementById('signal-check').textContent = signalStatus.last_check_ms ? formatTime(signalStatus.last_check_ms) : '--';
      document.getElementById('signal-status').textContent = signalStatus.reason || signalStatus.status || '--';

      drawKlines(d.klines || []);

      // Trade history
      const tbody = document.getElementById('trade-body');
      const history = d.trade_history || [];
      if (history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="color:#8b949e; padding: 8px 0;">No trades yet</td></tr>';
      } else {
        tbody.innerHTML = history.slice(0, 20).map(t => {
          const time = t.time ? formatTime(t.time) : '--';
          const cls = t.direction === 'UP' ? 'up' : 'down';
          const pnlStr = t.pnl !== 0 ? ((t.pnl >= 0 ? '+$' : '-$') + Math.abs(t.pnl).toFixed(2)) : '--';
          const redeemText = t.redemption_tx ? shortAddress(t.redemption_tx) : (t.redemption_error || (t.settled ? 'Settled' : 'Open'));
          const market = t.market_slug ? t.market_slug.replace('btc-updown-5m-', '') : '--';
          const signal = t.signal_reason || t.signal_trend || '--';
          return `<tr style="border-bottom: 1px solid #21262d;">
            <td style="color:#8b949e; padding: 5px 0;">${time}</td>
            <td style="padding: 5px 8px;"><span class="${cls}" style="font-weight:600;font-size:12px;">${t.direction}</span></td>
            <td style="padding: 5px 8px; font-family: monospace;">${market}</td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;">${t.price ? t.price.toFixed(4) : '--'}</td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;">$${t.size ? t.size.toFixed(2) : '--'}</td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;" class="${t.pnl > 0 ? 'up' : t.pnl < 0 ? 'down' : ''}">${pnlStr}</td>
            <td style="text-align:center; padding: 5px 8px; font-family: monospace;">${redeemText}</td>
            <td style="padding: 5px 8px;">${signal}</td>
          </tr>`;
        }).join('');
      }
    };
  </script>
</body>
</html>"""

    async def start(self) -> None:
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="warning")
        self._runner = uvicorn.Server(config)
        await self._runner.serve()

    def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast a message to all connected WebSocket clients."""
        for ws in list(self._ws_clients):
            asyncio.create_task(self._send_json(ws, data))

    async def _send_json(self, ws: WebSocket, data: dict[str, Any]) -> None:
        try:
            await ws.send_json(data)
        except Exception:
            if ws in self._ws_clients:
                self._ws_clients.remove(ws)
