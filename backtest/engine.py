"""
backtest/engine.py — Backtesting Framework
Test any strategy on historical data before risking real money.

Usage:
  python -m backtest.engine --symbol RELIANCE --days 60
  python -m backtest.engine --all --days 30
"""

import argparse
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logger = logging.getLogger("Backtest")


def run_backtest(symbol: str, days: int = 60, interval: str = "5minute") -> dict:
    from config.settings import (
        KITE_API_KEY, ACCESS_TOKEN_FILE, ACTIVE_STRATEGIES,
        ADX_MIN, CAPITAL_PER_TRADE, MAX_RISK_PER_TRADE,
        STOP_LOSS_PCT, TARGET_PCT, MIN_STRATEGY_CONFIDENCE,
        VOLUME_MULT,
    )
    import config.settings as cfg

    try:
        from data.market_data import MarketData
        from strategies.indicator_bundle import IndicatorBundle
        from strategies.signals import SignalGenerator
    except Exception as e:
        logger.error(f"Import error: {e}")
        return {}

    print(f"\n{'═'*60}")
    print(f"  BACKTEST: {symbol} | {days} days | {interval}")
    print(f"  Strategies: {', '.join(ACTIVE_STRATEGIES)}")
    print(f"{'═'*60}")

    try:
        md   = MarketData(KITE_API_KEY, str(ACCESS_TOKEN_FILE))
        md.load_instruments()
        df   = md.get_candles(symbol, interval, days=days)
    except Exception as e:
        print(f"[ERROR] Data fetch failed: {e}")
        return {}

    if df is None or len(df) < 60:
        print(f"[ERROR] Not enough data: {len(df) if df is not None else 0} candles")
        return {}

    print(f"Fetched {len(df)} candles for {symbol}")

    sgen = SignalGenerator(cfg)
    trades = []
    in_trade = False
    entry = sl = tgt = qty = action_t = entry_t = strats = None

    for i in range(60, len(df)):
        window = df.iloc[:i].copy()
        snap = IndicatorBundle.compute(window, symbol)
        if not snap.valid:
            continue

        price = snap.price

        if not in_trade:
            sig = sgen.generate(snap, CAPITAL_PER_TRADE)
            if sig and sig.action in ("BUY", "SELL"):
                in_trade = True
                entry = sig.price; sl = sig.stop_loss; tgt = sig.target
                qty = sig.quantity; action_t = sig.action
                entry_t = str(df["datetime"].iloc[i])[:16]
                strats = "+".join(sig.strategies)
        else:
            row = df.iloc[i]
            hit_tgt = hit_sl = False
            if action_t == "BUY":
                hit_tgt = row["high"] >= tgt
                hit_sl  = row["low"]  <= sl
            else:
                hit_tgt = row["low"]  <= tgt
                hit_sl  = row["high"] >= sl

            if hit_tgt or hit_sl:
                exit_p = tgt if hit_tgt else sl
                pnl = (exit_p - entry) * qty if action_t == "BUY" else (entry - exit_p) * qty
                trades.append({
                    "symbol": symbol, "action": action_t,
                    "entry": entry, "exit": exit_p, "qty": qty,
                    "pnl": round(pnl, 2), "reason": "TARGET" if hit_tgt else "SL",
                    "strategy": strats,
                    "entry_time": entry_t,
                    "exit_time": str(df["datetime"].iloc[i])[:16],
                })
                in_trade = False

    # ── Report ────────────────────────────────────────────────
    if not trades:
        print("No trades generated.")
        return {}

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    win_rate  = len(wins) / len(trades) * 100

    avg_win  = sum(t["pnl"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    pf = abs(avg_win * len(wins)) / abs(avg_loss * len(losses)) if losses and avg_loss else float("inf")

    print(f"\n{'─'*55}")
    print(f"  RESULTS — {symbol} ({days} days)")
    print(f"{'─'*55}")
    print(f"  Total trades    : {len(trades)}")
    print(f"  Wins            : {len(wins)} ({win_rate:.1f}%)")
    print(f"  Losses          : {len(losses)} ({100-win_rate:.1f}%)")
    print(f"  Total P&L       : ₹{total_pnl:+,.2f}")
    print(f"  Avg win         : ₹{avg_win:+.2f}")
    print(f"  Avg loss        : ₹{avg_loss:+.2f}")
    print(f"  Profit factor   : {pf:.2f}")
    print(f"{'─'*55}")
    print(f"\n  Last 10 trades:")
    print(f"  {'Date':<17} {'Dir':<5} {'Entry':>8} {'Exit':>8} {'P&L':>9} Reason")
    print(f"  {'─'*17} {'─'*5} {'─'*8} {'─'*8} {'─'*9} {'─'*10}")
    for t in trades[-10:]:
        print(f"  {t['entry_time']:<17} {t['action']:<5} "
              f"₹{t['entry']:>7.2f} ₹{t['exit']:>7.2f} "
              f"₹{t['pnl']:>+8.2f} {t['reason']}")
    print()

    return {
        "symbol": symbol, "trades": len(trades),
        "win_rate": win_rate, "total_pnl": total_pnl,
        "profit_factor": pf, "all_trades": trades,
    }


if __name__ == "__main__":
    from utils.logger import setup_logging
    setup_logging("WARNING")

    parser = argparse.ArgumentParser(description="Strategy Backtester")
    parser.add_argument("--symbol", default="RELIANCE")
    parser.add_argument("--days",   type=int, default=60)
    parser.add_argument("--interval", default="5minute")
    args = parser.parse_args()

    run_backtest(args.symbol, args.days, args.interval)
