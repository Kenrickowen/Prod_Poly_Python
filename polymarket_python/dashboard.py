"""FastAPI dashboard with WebSocket streaming of real-time state."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from polymarket_python.models import AppState

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
                self._ws_clients.remove(ws)

        @self.app.get("/state")
        async def get_state() -> dict[str, Any]:
            return self._state_snapshot()

    def _state_snapshot(self) -> dict[str, Any]:
        """Serialize current app state for JSON response / WebSocket."""
        window = self.state.window
        indicators = self.state.indicators

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
                "pnl": t.pnl,
                "settled": t.settled,
            })

        return {
            "last_price": self.state.last_price,
            "chainlink_price": self.state.chainlink_price,
            "poly_up_odds": self.state.poly_up_odds,
            "poly_down_odds": self.state.poly_down_odds,
            "window": {
                "start_ms": window.window_start_ms,
                "ptb": window.ptb,
                "ptb_source": window.ptb_source,
                "ptb_binance": window.ptb_binance,
                "ptb_chainlink": window.ptb_chainlink,
                "signal": signal_value,
                "traded": window.traded,
                "signal_evaluated": window.signal_evaluated,
                "first_in_window_candle_ms": window.first_in_window_candle_ms,
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
                "total_pnl": self.state.total_pnl,
                "current_balance": self.state.current_balance,
                "initial_balance": self.state.initial_balance,
            },
            "klines_count": len(self.state.klines),
            "last_kline_time_ms": self.state.last_kline_time_ms,
            "trade_history": trade_history,
        }

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
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; max-width: 1400px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
    .card h3 { color: #8b949e; margin: 0 0 12px 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
    .card .big-val { font-size: 26px; font-weight: 600; color: #58a6ff; }
    .card .small-val { font-size: 13px; color: #8b949e; margin-top: 4px; }
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
  </style>
</head>
<body>
  <h1>Polymarket BTC 5m Breakout</h1>
  <p class="subtitle">Strategy B — Binance BTC → Polymarket CLOB</p>
  <div id="ws-status"><span class="dot"></span>Connecting...</div>

  <div class="grid">
    <!-- Row 1: Price feeds -->
    <div class="card">
      <h3>BTC Price (Binance)</h3>
      <div class="big-val" id="last-price">--</div>
      <div class="small-val" id="last-price-time">--</div>
    </div>
    <div class="card">
      <h3>Chainlink BTC Feed</h3>
      <div class="big-val" id="chainlink-price">--</div>
      <div class="small-val">Polygon Oracle</div>
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
      </table>
    </div>
  </div>

  <div class="section-title">Trade History</div>
  <div class="card" style="max-width: 1400px; overflow: hidden;">
    <table id="trade-table" style="font-size: 12px;">
      <thead>
        <tr style="border-bottom: 1px solid #30363d;">
          <th style="text-align:left; padding: 4px 0; color:#8b949e; font-weight: normal;">Time</th>
          <th style="text-align:left; padding: 4px 8px; color:#8b949e; font-weight: normal;">Dir</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">Entry Odds</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">Size</th>
          <th style="text-align:right; padding: 4px 0; color:#8b949e; font-weight: normal;">PnL</th>
          <th style="text-align:center; padding: 4px 0; color:#8b949e; font-weight: normal;">Settled</th>
        </tr>
      </thead>
      <tbody id="trade-body">
        <tr><td colspan="6" style="color:#8b949e; padding: 8px 0;">No trades yet</td></tr>
      </tbody>
    </table>
  </div>

  <script>
    function formatTime(ts) {
      if (!ts) return '--';
      return new Date(ts).toLocaleTimeString();
    }
    function formatPrice(v) {
      if (!v) return '--';
      return '$' + v.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    function formatOdds(v) {
      if (!v) return '--';
      return v.toFixed(4);
    }

    const ws = new WebSocket(`ws://${location.host}/ws`);
    const statusEl = document.getElementById('ws-status');

    ws.onopen = () => { statusEl.className = 'connected'; statusEl.innerHTML = '<span class="dot"></span>Connected — live data'; };
    ws.onclose = () => { statusEl.className = 'disconnected'; statusEl.innerHTML = '<span class="dot"></span>Disconnected — reconnecting...'; setTimeout(() => location.reload(), 3000); };
    ws.onerror = () => { ws.close(); };

    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);

      // Price feeds
      document.getElementById('last-price').textContent = d.last_price ? d.last_price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--';
      document.getElementById('last-price-time').textContent = d.last_kline_time_ms ? formatTime(d.last_kline_time_ms) : '--';
      document.getElementById('chainlink-price').textContent = d.chainlink_price ? d.chainlink_price.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--';

      // Odds
      document.getElementById('poly-up').textContent = d.poly_up_odds ? formatOdds(d.poly_up_odds) : '--';
      document.getElementById('poly-down').textContent = d.poly_down_odds ? formatOdds(d.poly_down_odds) : '--';

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

      // Trade history
      const tbody = document.getElementById('trade-body');
      const history = d.trade_history || [];
      if (history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="color:#8b949e; padding: 8px 0;">No trades yet</td></tr>';
      } else {
        tbody.innerHTML = history.slice(0, 20).map(t => {
          const time = t.time ? new Date(t.time).toLocaleTimeString() : '--';
          const cls = t.direction === 'UP' ? 'up' : 'down';
          const pnlStr = t.pnl !== 0 ? ((t.pnl >= 0 ? '+$' : '-$') + Math.abs(t.pnl).toFixed(2)) : '--';
          const settledBadge = t.settled
            ? '<span style="background:#1f4d2a;color:#3fb950;padding:1px 6px;border-radius:3px;font-size:10px;">WIN</span>'
            : '<span style="background:#2d200a;color:#d29922;padding:1px 6px;border-radius:3px;font-size:10px;">OPEN</span>';
          return `<tr style="border-bottom: 1px solid #21262d;">
            <td style="color:#8b949e; padding: 5px 0;">${time}</td>
            <td style="padding: 5px 8px;"><span class="${cls}" style="font-weight:600;font-size:12px;">${t.direction}</span></td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;">${t.price ? t.price.toFixed(4) : '--'}</td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;">$${t.size ? t.size.toFixed(2) : '--'}</td>
            <td style="text-align:right; font-family: monospace; padding: 5px 0;" class="${t.pnl > 0 ? 'up' : t.pnl < 0 ? 'down' : ''}">${pnlStr}</td>
            <td style="text-align:center; padding: 5px 0;">${settledBadge}</td>
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
        for ws in self._ws_clients:
            try:
                asyncio.create_task(ws.send_json(data))
            except Exception:
                pass