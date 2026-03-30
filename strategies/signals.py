"""
strategies/signals.py
Signal generation from all 10 strategies.
Each strategy returns a score -1.0 to +1.0.
Aggregator combines them with weighted voting.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from strategies.indicator_bundle import IndicatorSnapshot

logger = logging.getLogger("Signals")


@dataclass
class TradeSignal:
    symbol:     str
    action:     str       # BUY | SELL | HOLD
    price:      float
    stop_loss:  float
    target:     float
    quantity:   int
    confidence: float     # 0.0–1.0
    strategies: list      # which strategies fired
    reason:     str
    indicators: dict = field(default_factory=dict)
    timestamp:  str  = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


class SignalGenerator:
    """
    Runs all active strategies against a computed IndicatorSnapshot,
    then aggregates via weighted voting.
    """

    STRATEGY_WEIGHTS = {
        "EMA_CROSSOVER":    1.0,
        "MACD_RSI":         0.9,
        "SUPERTREND":       1.1,   # High weight — very reliable intraday
        "VWAP_REVERSAL":    0.9,
        "BOLLINGER_SQUEEZE":1.0,
        "ICHIMOKU_CLOUD":   0.8,
        "OPENING_RANGE":    1.1,   # High weight in morning session
        "VOLUME_PRICE":     0.7,
        "MEAN_REVERSION":   0.8,
        "NEWS_SENTIMENT":   0.5,   # Lower weight — supplementary
    }

    def __init__(self, config, news_engine=None):
        self.cfg  = config
        self.news = news_engine

    def generate(
        self,
        snap: IndicatorSnapshot,
        capital_per_trade: float,
        news_score: float = 0.0,
    ) -> Optional[TradeSignal]:

        if not snap.valid:
            return None
        if snap.adx < self.cfg.ADX_MIN:
            return None   # Market not trending — skip

        buy_signals = {}
        sell_signals = {}

        for name in self.cfg.ACTIVE_STRATEGIES:
            fn = self._strategy_map().get(name)
            if fn is None:
                continue
            try:
                score = fn(snap, news_score)
                w = self.STRATEGY_WEIGHTS.get(name, 1.0)
                if score > 0.3:
                    buy_signals[name]  = score * w
                elif score < -0.3:
                    sell_signals[name] = abs(score) * w
            except Exception as e:
                logger.debug(f"{snap.symbol}/{name}: {e}")

        buy_conf  = self._aggregate(buy_signals)
        sell_conf = self._aggregate(sell_signals)

        if buy_conf < self.cfg.MIN_STRATEGY_CONFIDENCE and sell_conf < self.cfg.MIN_STRATEGY_CONFIDENCE:
            return None

        if buy_conf >= sell_conf and buy_conf >= self.cfg.MIN_STRATEGY_CONFIDENCE:
            action = "BUY"
            conf   = buy_conf
            fired  = list(buy_signals.keys())
        elif sell_conf > self.cfg.MIN_STRATEGY_CONFIDENCE:
            action = "SELL"
            conf   = sell_conf
            fired  = list(sell_signals.keys())
        else:
            return None

        # News veto
        if self.news and action == "BUY" and news_score < self.cfg.NEWS_BLOCK_THRESHOLD:
            return None
        if self.news and action == "SELL" and news_score > 0.35:
            return None

        # News boost (+5% max)
        if action == "BUY" and news_score > 0.2:
            conf = min(conf + news_score * 0.05, 0.97)

        # Position sizing: ATR-based 1% risk
        sl_dist  = max(snap.atr * 1.2, snap.price * self.cfg.STOP_LOSS_PCT)
        sl_dist  = max(sl_dist, snap.price * 0.005)   # minimum 0.5%
        risk_amt = capital_per_trade * self.cfg.MAX_RISK_PER_TRADE
        quantity = max(1, int(risk_amt / sl_dist))
        quantity = min(quantity, int(capital_per_trade / snap.price))

        if action == "BUY":
            stop_loss = round(snap.price - sl_dist, 2)
            target    = round(snap.price + sl_dist * 2.5, 2)
        else:
            stop_loss = round(snap.price + sl_dist, 2)
            target    = round(snap.price - sl_dist * 2.5, 2)

        reason = self._build_reason(snap, fired)

        return TradeSignal(
            symbol=snap.symbol, action=action, price=snap.price,
            stop_loss=stop_loss, target=target, quantity=quantity,
            confidence=conf, strategies=fired, reason=reason,
            indicators={
                "rsi": snap.rsi, "adx": snap.adx, "macd": snap.macd,
                "vwap_dev": snap.vwap_dev, "vol_ratio": snap.vol_ratio,
                "st_dir": snap.st_dir, "bb_pct": snap.bb_pct,
                "mfi": snap.mfi, "cmf": snap.cmf,
            },
        )

    # ─── Individual Strategies ────────────────────────────────

    def _ema_crossover(self, s: IndicatorSnapshot, _) -> float:
        cross_up = s.prev_ema9 <= s.prev_ema21 and s.ema_9 > s.ema_21
        cross_dn = s.prev_ema9 >= s.prev_ema21 and s.ema_9 < s.ema_21
        trend_ok_bull = s.price > s.ema_50 and s.plus_di > s.minus_di
        trend_ok_bear = s.price < s.ema_50 and s.minus_di > s.plus_di
        if cross_up and trend_ok_bull:
            return 0.85 + (0.1 if s.price > s.ema_200 else 0)
        if cross_dn and trend_ok_bear:
            return -(0.85 + (0.1 if not s.above_200 else 0))
        return 0.0

    def _macd_rsi(self, s: IndicatorSnapshot, _) -> float:
        macd_up = s.prev_macd <= s.prev_msig and s.macd > s.macd_signal
        macd_dn = s.prev_macd >= s.prev_msig and s.macd < s.macd_signal
        sk_up   = s.prev_stk < s.stoch_d and s.stoch_k > s.stoch_d and s.stoch_k < 80
        sk_dn   = s.prev_stk > s.stoch_d and s.stoch_k < s.stoch_d and s.stoch_k > 20
        rsi_ok  = 35 < s.rsi < 65
        vol_ok  = s.vol_ratio > self.cfg.VOLUME_MULT

        bull = sum([macd_up*0.4, sk_up*0.25, rsi_ok*0.2, vol_ok*0.15]) * (1 if s.above_50 else 0.7)
        bear = sum([macd_dn*0.4, sk_dn*0.25, rsi_ok*0.2, vol_ok*0.15]) * (1 if not s.above_50 else 0.7)

        if bull > 0.55: return bull
        if bear > 0.55: return -bear
        return 0.0

    def _supertrend(self, s: IndicatorSnapshot, _) -> float:
        flip_bull = s.prev_st_dir == -1 and s.st_dir == 1
        flip_bear = s.prev_st_dir == 1  and s.st_dir == -1
        post_sq   = not s.squeeze and s.prev_squeeze
        vol_ok    = s.vol_ratio > self.cfg.VOLUME_MULT

        if flip_bull and vol_ok:
            return 0.90 + (0.07 if post_sq else 0)
        if flip_bear and vol_ok:
            return -(0.90 + (0.07 if post_sq else 0))
        if s.st_dir == 1 and post_sq and s.rsi < 60:
            return 0.68
        if s.st_dir == -1 and post_sq and s.rsi > 40:
            return -0.68
        return 0.0

    def _vwap_reversal(self, s: IndicatorSnapshot, _) -> float:
        dev = s.vwap_dev; vs = s.vol_ratio > 2.0
        bounce_buy  = dev < -0.5 and s.rsi < 42 and s.mfi < 40 and vs
        bounce_sell = dev > 0.5  and s.rsi > 58 and s.mfi > 60 and vs
        brkout_buy  = -0.2 < dev < 0.3 and s.rsi > 50 and vs
        brkout_sell = -0.3 < dev < 0.2 and s.rsi < 50 and vs

        if bounce_buy  or brkout_buy:  return 0.75 if bounce_buy  else 0.65
        if bounce_sell or brkout_sell: return -(0.75 if bounce_sell else 0.65)
        return 0.0

    def _bollinger_squeeze(self, s: IndicatorSnapshot, _) -> float:
        if not (not s.squeeze and s.prev_squeeze):
            return 0.0
        up = s.price > s.bb_mid and s.rsi > 52 and s.vol_ratio > 1.8
        dn = s.price < s.bb_mid and s.rsi < 48 and s.vol_ratio > 1.8
        if up: return 0.80
        if dn: return -0.80
        return 0.0

    def _ichimoku(self, s: IndicatorSnapshot, _) -> float:
        above_cloud = s.price > max(s.span_a, s.span_b)
        below_cloud = s.price < min(s.span_a, s.span_b)
        tk_bull = s.tenkan > s.kijun
        tk_bear = s.tenkan < s.kijun
        if above_cloud and tk_bull and s.psar_bull and s.rsi > 50:
            return 0.78
        if below_cloud and tk_bear and not s.psar_bull and s.rsi < 50:
            return -0.78
        return 0.0

    def _opening_range(self, s: IndicatorSnapshot, _) -> float:
        t = datetime.now().strftime("%H:%M")
        if not ("09:45" <= t <= "11:45"):
            return 0.0
        if s.or_high is None or s.or_low is None:
            return 0.0
        rng = (s.or_high - s.or_low) / s.or_low * 100
        if rng > 3.0 or rng < 0.1:
            return 0.0
        if s.price > s.or_high * 1.002 and s.vol_ratio > 2.5:
            return 0.82
        if s.price < s.or_low  * 0.998 and s.vol_ratio > 2.5:
            return -0.82
        return 0.0

    def _volume_price(self, s: IndicatorSnapshot, _) -> float:
        obv_up = s.obv > s.prev_obv and s.price > s.ema_9
        obv_dn = s.obv < s.prev_obv and s.price < s.ema_9
        vol_surge = s.vol_ratio > 2.0
        cmf_bull = s.cmf > 0.1; cmf_bear = s.cmf < -0.1
        if obv_up and vol_surge and cmf_bull: return 0.70
        if obv_dn and vol_surge and cmf_bear: return -0.70
        return 0.0

    def _mean_reversion(self, s: IndicatorSnapshot, _) -> float:
        # Only at extremes: BB%B < 0.05 (oversold) or > 0.95 (overbought)
        rsi_os = s.rsi < 30; rsi_ob = s.rsi > 70
        bb_os  = s.bb_pct < 0.05; bb_ob = s.bb_pct > 0.95
        cci_os = s.cci < -150; cci_ob = s.cci > 150
        if (rsi_os and bb_os and s.williams_r < -90):
            return 0.72
        if (rsi_ob and bb_ob and s.williams_r > -10):
            return -0.72
        return 0.0

    def _news_sentiment_strat(self, s: IndicatorSnapshot, ns: float) -> float:
        if abs(ns) < 0.2: return 0.0
        return ns * 0.6   # Scale: max ±0.6

    # ─── Helpers ──────────────────────────────────────────────

    def _strategy_map(self) -> dict:
        return {
            "EMA_CROSSOVER":    self._ema_crossover,
            "MACD_RSI":         self._macd_rsi,
            "SUPERTREND":       self._supertrend,
            "VWAP_REVERSAL":    self._vwap_reversal,
            "BOLLINGER_SQUEEZE":self._bollinger_squeeze,
            "ICHIMOKU_CLOUD":   self._ichimoku,
            "OPENING_RANGE":    self._opening_range,
            "VOLUME_PRICE":     self._volume_price,
            "MEAN_REVERSION":   self._mean_reversion,
            "NEWS_SENTIMENT":   self._news_sentiment_strat,
        }

    def _aggregate(self, signals: dict) -> float:
        if not signals: return 0.0
        total_w = sum(self.STRATEGY_WEIGHTS.get(n, 1.0) for n in signals)
        weighted = sum(v for v in signals.values())
        avg = weighted / total_w
        bonus = 0.04 * (len(signals) - 1)   # Multi-strategy confirmation bonus
        return min(avg + bonus, 0.97)

    def _build_reason(self, s: IndicatorSnapshot, fired: list) -> str:
        parts = [
            f"ADX={s.adx:.1f}",
            f"RSI={s.rsi:.1f}",
            f"MACD={'▲' if s.macd > s.macd_signal else '▼'}",
            f"ST={'▲' if s.st_dir==1 else '▼'}",
            f"VWAP{s.vwap_dev:+.2f}%",
            f"Vol×{s.vol_ratio:.1f}",
            f"MFI={s.mfi:.1f}",
        ]
        return f"[{'+'.join(fired)}] {' | '.join(parts)}"
