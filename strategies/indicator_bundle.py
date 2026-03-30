"""
strategies/indicator_bundle.py  v2  (bug-fixed)
Computes 30+ indicators in one pass. All NaN-safe.
"""

import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ── helpers ──────────────────────────────────────────────────────────
def _f(v) -> float:
    """Convert any value to float safely; return 0.0 on NaN/inf/error."""
    try:
        x = float(v)
        return 0.0 if (math.isnan(x) or math.isinf(x)) else x
    except Exception:
        return 0.0

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


@dataclass
class IndicatorSnapshot:
    symbol:       str   = ""
    price:        float = 0.0
    timestamp:    str   = ""

    # ── Trend ──────────────────────────────────────────────
    ema_9:        float = 0.0
    ema_21:       float = 0.0
    ema_50:       float = 0.0
    ema_200:      float = 0.0
    sma_20:       float = 0.0
    tema_9:       float = 0.0
    dema_21:      float = 0.0
    wma_14:       float = 0.0
    prev_ema9:    float = 0.0
    prev_ema21:   float = 0.0

    # ── MACD ───────────────────────────────────────────────
    macd:         float = 0.0
    macd_signal:  float = 0.0
    macd_hist:    float = 0.0
    prev_macd:    float = 0.0
    prev_msig:    float = 0.0

    # ── Oscillators ────────────────────────────────────────
    rsi:          float = 50.0
    prev_rsi:     float = 50.0
    stoch_k:      float = 50.0
    stoch_d:      float = 50.0
    prev_stk:     float = 50.0
    williams_r:   float = -50.0
    cci:          float = 0.0
    roc_10:       float = 0.0
    roc_20:       float = 0.0
    momentum:     float = 0.0

    # ── Volume ─────────────────────────────────────────────
    vwap:         float = 0.0
    vwap_dev:     float = 0.0
    obv:          float = 0.0
    prev_obv:     float = 0.0
    mfi:          float = 50.0
    cmf:          float = 0.0
    vol_ratio:    float = 1.0
    vol_20ma:     float = 0.0

    # ── Volatility ─────────────────────────────────────────
    atr:          float = 0.0
    atr_pct:      float = 0.0
    bb_upper:     float = 0.0
    bb_mid:       float = 0.0
    bb_lower:     float = 0.0
    bb_pct:       float = 0.5
    bb_width:     float = 0.0
    kc_upper:     float = 0.0
    kc_lower:     float = 0.0
    squeeze:      bool  = False
    prev_squeeze: bool  = False
    hist_vol:     float = 0.0

    # ── Trend strength ─────────────────────────────────────
    adx:          float = 0.0
    plus_di:      float = 0.0
    minus_di:     float = 0.0
    aroon_up:     float = 0.0
    aroon_dn:     float = 0.0
    aroon_osc:    float = 0.0

    # ── Supertrend ─────────────────────────────────────────
    supertrend:   float = 0.0
    st_dir:       int   = 1
    prev_st_dir:  int   = 1

    # ── Parabolic SAR ──────────────────────────────────────
    psar:         float = 0.0
    psar_bull:    bool  = True

    # ── Ichimoku ───────────────────────────────────────────
    tenkan:       float = 0.0
    kijun:        float = 0.0
    span_a:       float = 0.0
    span_b:       float = 0.0

    # ── Pivot points ───────────────────────────────────────
    pivot:        float = 0.0
    r1: float = 0.0; r2: float = 0.0; r3: float = 0.0
    s1: float = 0.0; s2: float = 0.0; s3: float = 0.0

    # ── Opening range ──────────────────────────────────────
    or_high:      Optional[float] = None
    or_low:       Optional[float] = None

    # ── Flags ──────────────────────────────────────────────
    above_200:    bool  = True
    above_50:     bool  = True
    in_cloud:     bool  = False
    valid:        bool  = False


class IndicatorBundle:

    @staticmethod
    def compute(df: pd.DataFrame, symbol: str = "") -> IndicatorSnapshot:
        snap = IndicatorSnapshot(symbol=symbol)

        if df is None or len(df) < 30:
            return snap

        df = df.copy().reset_index(drop=True)
        c = df["close"].astype(float)
        h = df["high"].astype(float)
        l = df["low"].astype(float)
        v = df["volume"].astype(float)
        n = len(df)

        snap.price     = _f(c.iloc[-1])
        snap.timestamp = str(df["datetime"].iloc[-1])[:19] if "datetime" in df.columns else ""

        # ── EMAs ──────────────────────────────────────────────────
        e9   = _ema(c, 9)
        e21  = _ema(c, 21)
        e50  = _ema(c, min(50, n - 1))
        e200 = _ema(c, min(200, n - 1))

        snap.ema_9    = _f(e9.iloc[-1]);   snap.prev_ema9  = _f(e9.iloc[-2])
        snap.ema_21   = _f(e21.iloc[-1]);  snap.prev_ema21 = _f(e21.iloc[-2])
        snap.ema_50   = _f(e50.iloc[-1])
        snap.ema_200  = _f(e200.iloc[-1])
        snap.sma_20   = _f(_sma(c, min(20, n - 1)).iloc[-1])
        snap.above_200 = snap.price > snap.ema_200
        snap.above_50  = snap.price > snap.ema_50

        # DEMA / TEMA
        e21b = _ema(c, 21)
        snap.dema_21 = _f(2 * e21b.iloc[-1] - _ema(e21b, 21).iloc[-1])
        e1 = e9; e2 = _ema(e1, 9); e3 = _ema(e2, 9)
        snap.tema_9  = _f((3 * e1 - 3 * e2 + e3).iloc[-1])

        # WMA
        wlen = min(14, n)
        w = np.arange(1, wlen + 1)
        snap.wma_14 = _f(
            c.rolling(wlen).apply(lambda x: np.dot(x, w) / w.sum(), raw=True).iloc[-1]
        )

        # ── MACD ──────────────────────────────────────────────────
        mac = _ema(c, 12) - _ema(c, 26)
        sig = _ema(mac, 9)
        snap.macd       = _f(mac.iloc[-1]); snap.prev_macd = _f(mac.iloc[-2])
        snap.macd_signal = _f(sig.iloc[-1]); snap.prev_msig = _f(sig.iloc[-2])
        snap.macd_hist  = snap.macd - snap.macd_signal

        # ── RSI ───────────────────────────────────────────────────
        delta = c.diff()
        gain  = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi_s = 100 - 100 / (1 + rs)
        snap.rsi      = _f(rsi_s.iloc[-1])
        snap.prev_rsi = _f(rsi_s.iloc[-2])

        # ── Stochastic ────────────────────────────────────────────
        lo14  = l.rolling(min(14, n)).min()
        hi14  = h.rolling(min(14, n)).max()
        raw_k = 100 * (c - lo14) / (hi14 - lo14 + 1e-9)
        sk    = raw_k.rolling(3).mean()
        sd    = sk.rolling(3).mean()
        snap.stoch_k  = _f(sk.iloc[-1])
        snap.stoch_d  = _f(sd.iloc[-1])
        snap.prev_stk = _f(sk.iloc[-2])

        # ── Williams %R ───────────────────────────────────────────
        hhw = h.rolling(min(14, n)).max()
        llw = l.rolling(min(14, n)).min()
        snap.williams_r = _f((-100 * (hhw - c) / (hhw - llw + 1e-9)).iloc[-1])

        # ── CCI ───────────────────────────────────────────────────
        tp    = (h + l + c) / 3
        tp_ma = tp.rolling(min(20, n)).mean()
        tp_sd = tp.rolling(min(20, n)).std().replace(0, 1e-9)
        snap.cci = _f(((tp - tp_ma) / (0.015 * tp_sd)).iloc[-1])

        # ── ROC / Momentum ────────────────────────────────────────
        snap.roc_10  = _f((c / c.shift(10) - 1).iloc[-1] * 100) if n > 10 else 0.0
        snap.roc_20  = _f((c / c.shift(20) - 1).iloc[-1] * 100) if n > 20 else 0.0
        snap.momentum = _f((c - c.shift(10)).iloc[-1])             if n > 10 else 0.0

        # ── ATR ───────────────────────────────────────────────────
        tr    = pd.concat(
            [h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1
        ).max(axis=1)
        atr_s = tr.ewm(span=14, adjust=False).mean()
        snap.atr     = _f(atr_s.iloc[-1])
        snap.atr_pct = snap.atr / snap.price * 100 if snap.price else 0.0

        # ── Bollinger Bands ───────────────────────────────────────
        bb_m   = c.rolling(min(20, n)).mean()
        bb_std = c.rolling(min(20, n)).std().replace(0, 1e-9)
        bb_u   = bb_m + 2 * bb_std
        bb_l   = bb_m - 2 * bb_std
        snap.bb_upper = _f(bb_u.iloc[-1])
        snap.bb_mid   = _f(bb_m.iloc[-1])
        snap.bb_lower = _f(bb_l.iloc[-1])
        bb_range      = snap.bb_upper - snap.bb_lower
        snap.bb_pct   = float((snap.price - snap.bb_lower) / (bb_range + 1e-9))
        snap.bb_width = float(bb_range / (snap.bb_mid + 1e-9))

        # ── Keltner Channel + Squeeze ─────────────────────────────
        kc_m  = _ema(c, 20)
        kc_u  = kc_m + 1.5 * atr_s
        kc_l  = kc_m - 1.5 * atr_s
        snap.kc_upper     = _f(kc_u.iloc[-1])
        snap.kc_lower     = _f(kc_l.iloc[-1])
        snap.squeeze      = bool(bb_u.iloc[-1] < kc_u.iloc[-1] and bb_l.iloc[-1] > kc_l.iloc[-1])
        snap.prev_squeeze = bool(bb_u.iloc[-2] < kc_u.iloc[-2] and bb_l.iloc[-2] > kc_l.iloc[-2]) if n > 2 else False

        # ── Historical Volatility ─────────────────────────────────
        hv_raw = c.pct_change().rolling(min(20, n)).std().iloc[-1]
        snap.hist_vol = _f(hv_raw * math.sqrt(252) * 100)

        # ── VWAP ──────────────────────────────────────────────────
        cum_tv   = ((h + l + c) / 3 * v).cumsum()
        cum_v    = v.cumsum().replace(0, 1e-9)
        vwap_s   = cum_tv / cum_v
        snap.vwap    = _f(vwap_s.iloc[-1])
        snap.vwap_dev = float((snap.price - snap.vwap) / snap.vwap * 100) if snap.vwap else 0.0

        # ── OBV ───────────────────────────────────────────────────
        obv_s        = (np.sign(c.diff()) * v).fillna(0).cumsum()
        snap.obv      = _f(obv_s.iloc[-1])
        snap.prev_obv = _f(obv_s.iloc[-2])

        # ── MFI ───────────────────────────────────────────────────
        tp2    = (h + l + c) / 3
        raw_mf = tp2 * v
        pos_mf = raw_mf.where(tp2 > tp2.shift(), 0.0)
        neg_mf = raw_mf.where(tp2 < tp2.shift(), 0.0)
        mf_pos_sum = pos_mf.rolling(14).sum()
        mf_neg_sum = neg_mf.rolling(14).sum().replace(0, 1e-9)
        mfr        = mf_pos_sum / mf_neg_sum
        snap.mfi   = _f((100 - 100 / (1 + mfr)).iloc[-1])

        # ── CMF (fixed: Series / Series, then .iloc[-1]) ──────────
        mf_mult  = ((c - l) - (h - c)) / (h - l + 1e-9)
        cmf_num  = (mf_mult * v).rolling(min(20, n)).sum()
        cmf_den  = v.rolling(min(20, n)).sum().replace(0, 1e-9)
        snap.cmf = _f((cmf_num / cmf_den).iloc[-1])

        # ── Volume ratios ─────────────────────────────────────────
        v20          = v.rolling(min(20, n)).mean().replace(0, 1e-9)
        snap.vol_20ma  = _f(v20.iloc[-1])
        snap.vol_ratio = _f(v.iloc[-1] / v20.iloc[-1])

        # ── ADX ───────────────────────────────────────────────────
        up  = h.diff()
        dn  = -l.diff()
        pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=h.index)
        ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=l.index)
        pdi = 100 * pdm.ewm(span=14, adjust=False).mean() / atr_s.replace(0, 1e-9)
        ndi = 100 * ndm.ewm(span=14, adjust=False).mean() / atr_s.replace(0, 1e-9)
        dx  = 100 * (pdi - ndi).abs() / (pdi + ndi + 1e-9)
        adx_s       = dx.ewm(span=14, adjust=False).mean()
        snap.adx      = _f(adx_s.iloc[-1])
        snap.plus_di  = _f(pdi.iloc[-1])
        snap.minus_di = _f(ndi.iloc[-1])

        # ── Aroon ─────────────────────────────────────────────────
        aw = min(26, n - 1)
        if aw > 1:
            au = h.rolling(aw + 1).apply(lambda x: x.argmax() / aw * 100, raw=True)
            ad = l.rolling(aw + 1).apply(lambda x: x.argmin() / aw * 100, raw=True)
            snap.aroon_up  = _f(au.iloc[-1])
            snap.aroon_dn  = _f(ad.iloc[-1])
            snap.aroon_osc = snap.aroon_up - snap.aroon_dn

        # ── Supertrend ────────────────────────────────────────────
        st_mult = 3.0
        st_up   = (h + l) / 2 + st_mult * atr_s
        st_dn   = (h + l) / 2 - st_mult * atr_s
        st_line = pd.Series(np.nan, index=c.index)
        st_dir  = pd.Series(1,      index=c.index)
        st_line.iloc[0] = float(st_dn.iloc[0])

        for i in range(1, n):
            ps  = st_line.iloc[i - 1]
            pd_ = st_dir.iloc[i - 1]
            cc  = float(c.iloc[i])
            cu  = float(st_up.iloc[i]); cl = float(st_dn.iloc[i])

            if pd_ == 1:
                new_st = max(cl, ps) if cc > ps else cu
                new_d  = 1 if cc > new_st else -1
            else:
                new_st = min(cu, ps) if cc < ps else cl
                new_d  = -1 if cc < new_st else 1

            st_line.iloc[i] = new_st
            st_dir.iloc[i]  = new_d

        snap.supertrend  = _f(st_line.iloc[-1])
        snap.st_dir      = int(st_dir.iloc[-1])
        snap.prev_st_dir = int(st_dir.iloc[-2]) if n > 1 else 1

        # ── Parabolic SAR ─────────────────────────────────────────
        af, ep, rising = 0.02, float(l.iloc[0]), True
        sar_vals = [float(l.iloc[0])]
        for i in range(1, n):
            ps_ = sar_vals[-1]
            hi_ = float(h.iloc[i]); li_ = float(l.iloc[i])
            hi_prev = float(h.iloc[i - 1]); li_prev = float(l.iloc[i - 1])
            hi_pp   = float(h.iloc[max(0, i - 2)]); li_pp = float(l.iloc[max(0, i - 2)])
            if rising:
                ns_ = ps_ + af * (ep - ps_)
                ns_ = min(ns_, li_prev, li_pp)
                if hi_ > ep:
                    ep = hi_; af = min(af + 0.02, 0.2)
                if li_ < ns_:
                    rising = False; ns_ = ep; ep = li_; af = 0.02
            else:
                ns_ = ps_ - af * (ps_ - ep)
                ns_ = max(ns_, hi_prev, hi_pp)
                if li_ < ep:
                    ep = li_; af = min(af + 0.02, 0.2)
                if hi_ > ns_:
                    rising = True; ns_ = ep; ep = hi_; af = 0.02
            sar_vals.append(ns_)
        snap.psar      = _f(sar_vals[-1])
        snap.psar_bull = snap.price > snap.psar

        # ── Ichimoku ──────────────────────────────────────────────
        def _midline(period):
            return (h.rolling(period).max() + l.rolling(period).min()) / 2

        tenkan = _midline(9)
        kijun  = _midline(26)
        span_a = ((tenkan + kijun) / 2).shift(26)
        span_b = _midline(52).shift(26)
        snap.tenkan = _f(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else snap.price
        snap.kijun  = _f(kijun.iloc[-1])  if not pd.isna(kijun.iloc[-1])  else snap.price
        snap.span_a = _f(span_a.iloc[-1]) if not pd.isna(span_a.iloc[-1]) else snap.price
        snap.span_b = _f(span_b.iloc[-1]) if not pd.isna(span_b.iloc[-1]) else snap.price
        cloud_top = max(snap.span_a, snap.span_b)
        cloud_bot = min(snap.span_a, snap.span_b)
        snap.in_cloud = cloud_bot <= snap.price <= cloud_top

        # ── Pivot Points ──────────────────────────────────────────
        ph = _f(h.iloc[-2]); pl_ = _f(l.iloc[-2]); pc = _f(c.iloc[-2])
        pp = (ph + pl_ + pc) / 3
        snap.pivot = pp
        snap.r1 = 2 * pp - pl_; snap.r2 = pp + (ph - pl_); snap.r3 = ph + 2 * (pp - pl_)
        snap.s1 = 2 * pp - ph;  snap.s2 = pp - (ph - pl_); snap.s3 = pl_ - 2 * (ph - pp)

        # ── Opening Range ─────────────────────────────────────────
        if "datetime" in df.columns:
            try:
                times = pd.to_datetime(df["datetime"]).dt.strftime("%H:%M")
                orb   = df[times <= "09:45"]
                if len(orb) > 0:
                    snap.or_high = float(orb["high"].max())
                    snap.or_low  = float(orb["low"].min())
            except Exception:
                pass

        # ── Final NaN sweep ───────────────────────────────────────
        for k, val in snap.__dict__.items():
            if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                setattr(snap, k, 0.0)

        snap.valid = True
        return snap
