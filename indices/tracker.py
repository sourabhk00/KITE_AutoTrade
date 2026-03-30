"""
indices/tracker.py
==================
Tracks live levels for all 17 indices: Nifty 50, Sensex,
Bank Nifty, Midcap 100, Bankex, and all sector indices.
Used by dashboard and market-regime filter.
"""

import logging
import time
import threading
from datetime import datetime
from typing import Optional

logger = logging.getLogger("IndexTracker")


class IndexTracker:
    """
    Fetches and caches live index levels from Kite API.
    Updates every 10 seconds in a background thread.
    """

    INDEX_SYMBOLS = {
        # NSE indices
        "NIFTY 50":          "NSE:NIFTY 50",
        "NIFTY BANK":        "NSE:NIFTY BANK",
        "NIFTY 100":         "NSE:NIFTY 100",
        "NIFTY MIDCAP 100":  "NSE:NIFTY MIDCAP 100",
        "NIFTY IT":          "NSE:NIFTY IT",
        "NIFTY PHARMA":      "NSE:NIFTY PHARMA",
        "NIFTY AUTO":        "NSE:NIFTY AUTO",
        "NIFTY FIN SERVICE": "NSE:NIFTY FIN SERVICE",
        "NIFTY ENERGY":      "NSE:NIFTY ENERGY",
        "NIFTY FMCG":        "NSE:NIFTY FMCG",
        "NIFTY METAL":       "NSE:NIFTY METAL",
        "NIFTY REALTY":      "NSE:NIFTY REALTY",
        "NIFTY COMMODITIES": "NSE:NIFTY COMMODITIES",
        "NIFTY CONSUMPTION": "NSE:NIFTY CONSUMPTION",
        "NIFTY DIV OPPS 50": "NSE:NIFTY DIV OPPS 50",
        "INDIA VIX":         "NSE:INDIA VIX",
        # BSE indices
        "SENSEX":            "BSE:SENSEX",
        "BANKEX":            "BSE:BANKEX",
    }

    def __init__(self, kite_client):
        self.kite   = kite_client
        self._cache : dict[str, dict] = {}
        self._lock  = threading.Lock()
        self._running = False

    def start(self):
        """Start background refresh thread."""
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True, name="IndexTracker")
        t.start()
        logger.info("Index tracker started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._fetch_all()
            except Exception as e:
                logger.debug(f"Index fetch error: {e}")
            time.sleep(10)

    def _fetch_all(self):
        symbols = list(self.INDEX_SYMBOLS.values())
        # Kite LTP accepts max ~500 at once; indices are few so this is fine
        try:
            quotes = self.kite.ltp(symbols)
        except Exception as e:
            logger.debug(f"Index LTP error: {e}")
            return

        with self._lock:
            for name, exchange_sym in self.INDEX_SYMBOLS.items():
                q = quotes.get(exchange_sym, {})
                ltp = q.get("last_price", 0)
                if ltp:
                    prev = self._cache.get(name, {}).get("ltp", ltp)
                    self._cache[name] = {
                        "ltp":    ltp,
                        "prev":   prev,
                        "chg":    ltp - prev,
                        "chg_pct": (ltp - prev) / prev * 100 if prev else 0,
                        "ts":     datetime.now().strftime("%H:%M:%S"),
                    }

    def get(self, name: str) -> dict:
        with self._lock:
            return dict(self._cache.get(name, {}))

    def get_all(self) -> dict:
        with self._lock:
            return dict(self._cache)

    def get_ltp(self, name: str) -> float:
        return self.get(name).get("ltp", 0.0)

    def market_regime(self) -> str:
        """
        Determine overall market regime from Nifty 50 and VIX.
        Returns: BULLISH | BEARISH | SIDEWAYS | VOLATILE
        """
        nifty = self.get("NIFTY 50")
        vix   = self.get("INDIA VIX")

        if not nifty:
            return "UNKNOWN"

        chg_pct = nifty.get("chg_pct", 0)
        vix_val = vix.get("ltp", 15)

        if vix_val > 25:
            return "VOLATILE"
        if chg_pct > 0.5:
            return "BULLISH"
        if chg_pct < -0.5:
            return "BEARISH"
        return "SIDEWAYS"

    def hot_sectors(self) -> list[str]:
        """Return top 3 best-performing sector indices today."""
        sectors = {
            "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO",
            "NIFTY FMCG", "NIFTY METAL", "NIFTY ENERGY",
            "NIFTY FIN SERVICE", "NIFTY REALTY",
        }
        ranked = []
        with self._lock:
            for s in sectors:
                d = self._cache.get(s, {})
                if d:
                    ranked.append((s, d.get("chg_pct", 0)))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in ranked[:3]]
