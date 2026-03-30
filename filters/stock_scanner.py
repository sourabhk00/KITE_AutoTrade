"""
filters/stock_scanner.py
Ranks all watchlist stocks by opportunity score every ~15 minutes.
Filters out: penny stocks, low volume, no volatility, sideways chop.
Returns ranked list with best opportunities at the top.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger("Scanner")


class StockScanner:
    def __init__(self, config, market_data):
        self.cfg  = config
        self.md   = market_data

    def scan_all(self) -> list[str]:
        candidates = []
        token_map  = self.md.token_map if hasattr(self.md, "token_map") else {}

        for sym in self.cfg.WATCHLIST:
            if sym not in token_map:
                continue
            try:
                score, ok = self._score(sym)
                if ok:
                    candidates.append((sym, score))
            except Exception as e:
                logger.debug(f"Scan error {sym}: {e}")

        candidates.sort(key=lambda x: x[1], reverse=True)
        ranked = [s for s, _ in candidates]
        if ranked:
            logger.info(f"Scanner: {len(ranked)}/{len(self.cfg.WATCHLIST)} passed | Top5: {ranked[:5]}")
        return ranked

    def _score(self, symbol: str) -> tuple[float, bool]:
        df = self.md.get_candles(symbol, self.cfg.CANDLE_INTERVAL, days=3)
        if df is None or len(df) < 25:
            return 0.0, False

        c = df["close"]; h = df["high"]; l = df["low"]; v = df["volume"]
        price = float(c.iloc[-1])

        # Price filter
        if price < self.cfg.MIN_PRICE or price > self.cfg.MAX_PRICE:
            return 0.0, False

        # ATR % filter
        tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
        atr_pct = float(tr.ewm(span=14,adjust=False).mean().iloc[-1]) / price * 100
        if atr_pct < self.cfg.MIN_ATR_PCT or atr_pct > self.cfg.MAX_ATR_PCT:
            return 0.0, False

        # Volume filter
        vol_ma = float(v.rolling(20).mean().iloc[-1])
        vol_ratio = float(v.iloc[-1]) / (vol_ma + 1e-9)
        if vol_ratio < 0.5:
            return 0.0, False

        # Gap filter — skip extreme gappers
        gap = abs(float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100 if len(c) > 1 else 0
        if gap > 4.0:
            return 0.0, False

        # Sideways chop filter
        rng = (float(h.iloc[-20:].max()) - float(l.iloc[-20:].min())) / price * 100
        if rng < 0.8:
            return 0.0, False

        # Composite score
        roc5 = abs(float(c.iloc[-1]/c.iloc[-6]-1)*100) if len(c)>6 else 0
        score = (
            min(vol_ratio / 3.0, 0.30) +
            min(atr_pct / self.cfg.MAX_ATR_PCT, 0.25) +
            min(roc5 / 2.0, 0.25) +
            min(rng / 5.0, 0.20)
        )
        # Tier-1 bonus
        if symbol in self.cfg.NIFTY_50[:20]:
            score += 0.08

        return round(score, 4), True
