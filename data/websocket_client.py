"""
data/websocket_client.py
Real-time market data streaming via Kite WebSocket (KiteTicker).
Streams live ticks for all watched symbols — price updates every ~100ms.
"""

import logging
import threading
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger("WebSocket")


class TickStore:
    """Thread-safe in-memory tick store, shared with strategies."""

    def __init__(self):
        self._data: dict[int, dict] = {}   # token → latest tick
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []

    def update(self, ticks: list):
        with self._lock:
            for tick in ticks:
                token = tick["instrument_token"]
                self._data[token] = {
                    "ltp":    tick.get("last_price", 0),
                    "volume": tick.get("volume", 0),
                    "bid":    tick.get("depth", {}).get("buy", [{}])[0].get("price", 0),
                    "ask":    tick.get("depth", {}).get("sell", [{}])[0].get("price", 0),
                    "oi":     tick.get("oi", 0),
                    "ts":     datetime.now(),
                }
        for cb in self._callbacks:
            try:
                cb(ticks)
            except Exception as e:
                logger.debug(f"Tick callback error: {e}")

    def get_ltp(self, token: int) -> float:
        with self._lock:
            return self._data.get(token, {}).get("ltp", 0.0)

    def get_tick(self, token: int) -> dict:
        with self._lock:
            return dict(self._data.get(token, {}))

    def on_tick(self, callback: Callable):
        self._callbacks.append(callback)


class WebSocketClient:
    """
    KiteTicker wrapper for real-time price streaming.
    Falls back gracefully to REST polling if WebSocket fails.
    """

    def __init__(self, api_key: str, access_token: str):
        self.api_key      = api_key
        self.access_token = access_token
        self.tick_store   = TickStore()
        self._ticker      = None
        self._tokens: list[int] = []
        self._running     = False
        self._use_fallback = False

    def subscribe(self, tokens: list[int]):
        """Subscribe to tick stream for given instrument tokens."""
        self._tokens = list(set(tokens))
        logger.info(f"Subscribing to {len(self._tokens)} instruments")

    def start(self):
        """Start WebSocket connection in background thread."""
        try:
            from kiteconnect import KiteTicker
            self._ticker = KiteTicker(self.api_key, self.access_token)
            self._ticker.on_ticks  = self._on_ticks
            self._ticker.on_connect = self._on_connect
            self._ticker.on_close  = self._on_close
            self._ticker.on_error  = self._on_error
            self._running = True
            t = threading.Thread(target=self._ticker.connect, kwargs={"threaded": True}, daemon=True)
            t.start()
            logger.info("WebSocket streaming started")
        except Exception as e:
            logger.warning(f"WebSocket failed ({e}) — using REST fallback")
            self._use_fallback = True

    def stop(self):
        self._running = False
        if self._ticker:
            try:
                self._ticker.close()
            except Exception:
                pass

    def get_ltp_from_stream(self, token: int) -> Optional[float]:
        ltp = self.tick_store.get_ltp(token)
        return ltp if ltp > 0 else None

    # ── Ticker callbacks ──────────────────────────────────────

    def _on_connect(self, ws, response):
        if self._tokens:
            ws.subscribe(self._tokens)
            ws.set_mode(ws.MODE_FULL, self._tokens)
            logger.info(f"WebSocket connected — streaming {len(self._tokens)} symbols")

    def _on_ticks(self, ws, ticks):
        self.tick_store.update(ticks)

    def _on_close(self, ws, code, reason):
        logger.warning(f"WebSocket closed: {code} {reason}")

    def _on_error(self, ws, code, reason):
        logger.error(f"WebSocket error: {code} {reason}")
