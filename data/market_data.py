"""
data/market_data.py
Handles all market data fetching — historical candles, quotes, LTP,
instruments, and index data from the Zerodha Kite API.
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger("MarketData")


class MarketData:
    """Unified market data interface for the trading bot."""

    def __init__(self, api_key: str, access_token_file: str):
        try:
            from kiteconnect import KiteConnect
        except ImportError:
            logger.critical("kiteconnect not installed. Run: pip install kiteconnect")
            sys.exit(1)

        self.kite = KiteConnect(api_key=api_key)
        self._load_token(access_token_file)
        self._instruments_cache: list = []
        self._token_map: dict[str, int] = {}
        self._verify()

    # ─── Auth ─────────────────────────────────────────────────

    def _load_token(self, path: str):
        p = Path(path)
        if not p.exists():
            logger.critical(f"Access token not found at {path}. Run login.py first.")
            sys.exit(1)
        token = p.read_text().strip()
        self.kite.set_access_token(token)

    def _verify(self):
        try:
            profile = self.kite.profile()
            logger.info(f"Connected: {profile['user_name']} ({profile['user_id']})")
        except Exception as e:
            logger.critical(f"Kite connection failed: {e}")
            sys.exit(1)

    # ─── Instruments ──────────────────────────────────────────

    def load_instruments(self, exchange: str = "NSE") -> dict[str, int]:
        """Load all instruments and build symbol→token map."""
        logger.info("Loading NSE instruments...")
        try:
            instruments = self.kite.instruments(exchange)
            self._instruments_cache = instruments
            for inst in instruments:
                sym = inst["tradingsymbol"]
                if inst.get("segment") in ("NSE", "NSE-EQ"):
                    self._token_map[sym] = inst["instrument_token"]
            logger.info(f"Loaded {len(self._token_map)} instruments")
            return self._token_map
        except Exception as e:
            logger.error(f"Instrument load failed: {e}")
            return {}

    def get_token(self, symbol: str) -> Optional[int]:
        return self._token_map.get(symbol)

    def build_token_map(self, symbols: list[str]) -> dict[str, int]:
        return {s: self._token_map[s] for s in symbols if s in self._token_map}

    # ─── Historical Data ──────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        interval: str = "5minute",
        days: int = 5,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles for a symbol.
        Returns DataFrame with columns: datetime, open, high, low, close, volume
        """
        token = self.get_token(symbol)
        if not token:
            return pd.DataFrame()

        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=days)

        retries = 3
        for attempt in range(retries):
            try:
                data = self.kite.historical_data(
                    token,
                    from_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    to_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    interval,
                    continuous=False,
                )
                if not data:
                    return pd.DataFrame()
                df = pd.DataFrame(data)
                df.columns = [c.lower() for c in df.columns]
                df = df.rename(columns={"date": "datetime"})
                df["datetime"] = pd.to_datetime(df["datetime"])
                return df.reset_index(drop=True)
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1)
                else:
                    logger.debug(f"Candle fetch failed {symbol}: {e}")
        return pd.DataFrame()

    def get_daily_candles(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """Fetch daily OHLCV for trend analysis."""
        return self.get_candles(symbol, interval="day", days=days)

    # ─── Quotes ───────────────────────────────────────────────

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        """Last traded prices for multiple symbols."""
        exchange_symbols = [f"NSE:{s}" for s in symbols]
        try:
            quotes = self.kite.ltp(exchange_symbols)
            return {
                sym.replace("NSE:", ""): data["last_price"]
                for sym, data in quotes.items()
            }
        except Exception as e:
            logger.error(f"LTP fetch failed: {e}")
            return {}

    def get_quote(self, symbol: str) -> dict:
        """Full quote: OHLC, volume, circuit limits, depth."""
        try:
            q = self.kite.quote(f"NSE:{symbol}")
            return q.get(f"NSE:{symbol}", {})
        except Exception as e:
            logger.error(f"Quote failed {symbol}: {e}")
            return {}

    def get_ohlc(self, symbols: list[str]) -> dict[str, dict]:
        """Day's OHLC + LTP for multiple symbols efficiently."""
        exchange_symbols = [f"NSE:{s}" for s in symbols]
        try:
            return self.kite.ohlc(exchange_symbols)
        except Exception as e:
            logger.error(f"OHLC fetch failed: {e}")
            return {}

    # ─── Index Data ───────────────────────────────────────────

    def get_index_ltp(self) -> dict[str, float]:
        """Fetch Nifty 50, Bank Nifty, India VIX levels."""
        indices = {
            "NIFTY 50":   256265,
            "NIFTY BANK": 260105,
        }
        result = {}
        for name, token in indices.items():
            try:
                q = self.kite.ltp(f"NSE:{name}")
                result[name] = q.get(f"NSE:{name}", {}).get("last_price", 0)
            except Exception:
                pass
        return result

    # ─── Account ──────────────────────────────────────────────

    def get_margins(self) -> dict:
        try:
            return self.kite.margins()
        except Exception as e:
            logger.error(f"Margins fetch failed: {e}")
            return {}

    def get_available_cash(self) -> float:
        try:
            m = self.kite.margins()
            return m.get("equity", {}).get("available", {}).get("live_balance", 0.0)
        except Exception:
            return 0.0

    def get_positions(self) -> dict:
        try:
            return self.kite.positions()
        except Exception as e:
            logger.error(f"Positions fetch failed: {e}")
            return {}
