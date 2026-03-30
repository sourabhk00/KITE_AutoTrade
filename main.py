"""
main.py v7 — Complete Auto Trading Bot
=======================================
  • User sets capital + daily target + SL via dashboard or CLI
  • Bot auto-buys and auto-sells based on multi-strategy analysis
  • GTT orders placed on Zerodha — survive disconnections
  • Order log tracks every trade with timestamp
  • Start/Stop from dashboard without restarting

Run: python login.py  →  python paper_trading.py  or  python live_trading.py
Dashboard: http://localhost:8050
"""

import os, sys, time, logging, json, signal, threading
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from utils.logger import setup_logging
setup_logging()
logger = logging.getLogger("Main")

import config.settings as cfg
from core.session            import TradingSession, get_session, set_session
from data.market_data        import MarketData
from data.websocket_client   import WebSocketClient
from strategies.indicator_bundle import IndicatorBundle
from strategies.signals      import SignalGenerator
from execution.order_manager import OrderManager
from execution.risk_manager  import RiskManager, OpenPosition
from utils.notifier          import Notifier
from utils.helpers           import now_ist
from indices.tracker         import IndexTracker
from ipo.analyzer            import IPOAnalyzer
from visualization.dashboard import start_dashboard


class TradingBot:

    def __init__(self, session: TradingSession = None):
        self._running     = False
        self._paused      = False
        self._scan_count  = 0
        self._ranked_list = list(cfg.WATCHLIST_TIER1 if hasattr(cfg,"WATCHLIST_TIER1") else cfg.WATCHLIST)
        self._strat_stats = {s: {"signals":0,"wins":0,"losses":0} for s in cfg.ACTIVE_STRATEGIES}

        # Apply session to config
        self._session = session or get_session()
        self._session.apply_to_config(cfg)
        logger.info(f"Session: {self._session.summary()}")

        self._setup()

    # ── Init ─────────────────────────────────────────────────────────

    def _setup(self):
        logger.info("Connecting to Zerodha Kite API...")
        self._md        = MarketData(cfg.KITE_API_KEY, str(cfg.ACCESS_TOKEN_FILE))
        self._token_map = self._md.load_instruments("NSE")

        self._orders = OrderManager(self._md.kite, paper_mode=cfg.PAPER_TRADING)
        self._risk   = RiskManager(cfg)
        self._risk._strat_stats = self._strat_stats
        self._risk.order_log    = []   # for dashboard order log

        self._indices = IndexTracker(self._md.kite)
        self._indices.start()

        self._ipo     = IPOAnalyzer(cfg, self._md.kite)
        self._news    = self._load_news()
        self._sgen    = SignalGenerator(cfg, news_engine=self._news)
        self._notify  = Notifier(cfg)
        self._ws      = None
        self._init_ws()

        # Bot controller exposed to dashboard
        self._controller = {
            "running": False,
            "start":   self._dashboard_start,
            "stop":    self._dashboard_stop,
        }

        try:
            start_dashboard(
                self._risk,
                lambda s, i: self._md.get_candles(s, i, days=5),
                self._indices,
                self._ipo,
                self._session,
                self._controller,
                cfg,
            )
        except Exception as e:
            logger.warning(f"Dashboard: {e}")

    def _init_ws(self):
        try:
            token = Path(cfg.ACCESS_TOKEN_FILE).read_text().strip()
            self._ws = WebSocketClient(cfg.KITE_API_KEY, token)
            toks = [t for s,t in self._token_map.items() if s in cfg.WATCHLIST][:200]
            self._ws.subscribe(toks)
            self._ws.start()
        except Exception as e:
            logger.warning(f"WebSocket: {e}")

    def _load_news(self):
        try:
            from news.sentiment import SentimentEngine
            return SentimentEngine(cfg)
        except Exception:
            return None

    # ── Dashboard start/stop controls ────────────────────────────────

    def _dashboard_start(self):
        if self._running:
            logger.info("Bot already running")
            return
        self._running = True
        t = threading.Thread(target=self._trading_loop, daemon=True, name="TradingLoop")
        t.start()
        logger.info("Bot started from dashboard")

    def _dashboard_stop(self):
        logger.info("Bot stop requested from dashboard")
        self._running = False

    # ── Main entry ───────────────────────────────────────────────────

    def run(self):
        """Called by paper_trading.py / live_trading.py directly."""
        signal.signal(signal.SIGINT,  self._stop_signal)
        signal.signal(signal.SIGTERM, self._stop_signal)
        self._banner()
        self._notify.bot_started(cfg.PAPER_TRADING)

        # Wait for market open
        if not self._in_market():
            logger.info(f"Waiting for market open ({cfg.MARKET_OPEN})...")
            while not self._in_market():
                time.sleep(20)

        self._running = True
        self._refresh_list()
        self._check_ipos()
        self._trading_loop()

    def _trading_loop(self):
        while self._running:
            t = now_ist()
            if t > cfg.MARKET_CLOSE: break
            if t >= cfg.SQUARE_OFF:
                self._sq_all("EOD"); break

            self._monitor()

            if self._risk.total_pnl >= cfg.DAILY_TARGET:
                logger.info("Daily target hit!")
                self._notify.daily_target(self._risk.total_pnl)
                self._coast(); break
            if self._risk.total_pnl <= -cfg.DAILY_LOSS_LIMIT:
                logger.warning("Loss limit hit!")
                self._notify.daily_loss_limit(self._risk.total_pnl)
                self._sq_all("LOSS_LIMIT"); break

            if self._can_enter(t):
                if self._scan_count % 16 == 0:
                    self._refresh_list()
                    # Re-apply session parameters (user may have changed via dashboard)
                    self._session.apply_to_config(cfg)
                self._scan()

            self._scan_count += 1
            if self._scan_count % 10 == 0:
                logger.info(f"[#{self._scan_count}] {self._risk.status_line()} "
                            f"| {self._indices.market_regime()} "
                            f"| VIX={self._indices.get_ltp('INDIA VIX'):.1f}")

            time.sleep(cfg.SCAN_INTERVAL)

        self._shutdown()

    # ── Scanner ──────────────────────────────────────────────────────

    def _refresh_list(self):
        try:
            from filters.stock_scanner import StockScanner
            ranked = StockScanner(cfg, self._md).scan_all()
            if ranked:
                # Hot sector prioritisation
                hot = set()
                sector_map = {
                    "NIFTY IT": cfg.NIFTY_IT, "NIFTY PHARMA": cfg.NIFTY_PHARMA,
                    "NIFTY AUTO": cfg.NIFTY_AUTO, "NIFTY FMCG": cfg.NIFTY_FMCG,
                    "NIFTY METAL": cfg.NIFTY_METAL, "NIFTY FIN SERVICE": cfg.NIFTY_FIN_SVC,
                    "NIFTY ENERGY": cfg.NIFTY_ENERGY,
                }
                for s in self._indices.hot_sectors():
                    hot.update(sector_map.get(s, []))
                priority = [s for s in ranked if s in hot]
                rest     = [s for s in ranked if s not in hot]
                self._ranked_list = priority + rest
                logger.info(f"Ranked {len(self._ranked_list)} | Hot: {self._indices.hot_sectors()}")
        except Exception as e:
            logger.warning(f"Scanner: {e}")

    def _check_ipos(self):
        if not cfg.IPO_ENABLED: return
        try:
            recs = self._ipo.get_recommendations()
            for r in recs:
                if r["recommendation"] == "APPLY":
                    logger.info(f"IPO APPLY: {r['name']} | {r['reason']} | Score={r['score']:.2f}")
        except Exception as e:
            logger.warning(f"IPO: {e}")

    # ── Scan & Execute ────────────────────────────────────────────────

    def _scan(self):
        logger.info(f"\n── #{self._scan_count} | {datetime.now():%H:%M:%S} "
                    f"| P&L=₹{self._risk.total_pnl:+.0f} | {self._indices.market_regime()} ──")

        vix = self._indices.get_ltp("INDIA VIX")
        if vix > 25:
            logger.info(f"VIX={vix:.1f} > 25 — skipping new entries"); return

        for sym in self._ranked_list:
            if not self._running: break
            if len(self._risk.positions) >= cfg.MAX_POSITIONS: break
            if sym in self._risk.positions: continue

            df = self._md.get_candles(sym, cfg.CANDLE_INTERVAL, days=5)
            if df is None or len(df) < 50: time.sleep(0.15); continue

            try:
                snap = IndicatorBundle.compute(df, sym)
            except Exception as e:
                logger.debug(f"Ind {sym}: {e}"); time.sleep(0.15); continue

            if not snap.valid: time.sleep(0.15); continue

            ns = 0.0
            if self._news:
                try: ns = self._news.get_stock_sentiment(sym)["score"]
                except Exception: pass

            try:
                sig = self._sgen.generate(snap, cfg.CAPITAL_PER_TRADE, ns)
            except Exception as e:
                logger.debug(f"Sig {sym}: {e}"); time.sleep(0.15); continue

            if sig and sig.action in ("BUY","SELL"):
                self._execute(sig)

            time.sleep(0.3)

    def _execute(self, sig):
        ok, reason = self._risk.can_enter(
            symbol=sig.symbol, action=sig.action, price=sig.price,
            stop_loss=sig.stop_loss, quantity=sig.quantity,
            available_cash=self._md.get_available_cash(),
        )
        if not ok: logger.debug(f"[BLOCKED] {sig.symbol}: {reason}"); return

        qty = self._risk.size_position(
            price=sig.price, stop_loss=sig.stop_loss,
            confidence=sig.confidence, capital_per_trade=cfg.CAPITAL_PER_TRADE,
        )
        if qty < 1: return
        sig.quantity = qty

        logger.info(
            f"\n  AUTO ORDER: {sig.symbol} {sig.action} | [{'+'.join(sig.strategies)}]\n"
            f"  ₹{sig.price:.2f}  SL=₹{sig.stop_loss:.2f}  TGT=₹{sig.target:.2f}"
            f"  Qty={qty}  Conf={sig.confidence:.0%}"
        )

        oid = self._orders.market_order(sig.symbol, sig.action, qty,
                                         tag=f"V7_{(sig.strategies[0] if sig.strategies else 'BOT')[:4]}")
        if not oid: return

        self._orders.place_gtt_oco(sig.symbol, qty, sig.price,
                                    sig.stop_loss, sig.target, sig.action)

        pos = OpenPosition(
            symbol=sig.symbol, action=sig.action, entry_price=sig.price,
            quantity=qty, stop_loss=sig.stop_loss, target=sig.target,
            trailing_sl=sig.stop_loss, order_id=oid,
            current_price=sig.price, strategy="+".join(sig.strategies),
        )
        self._risk.open_position(pos)
        self._notify.trade_opened(sig.symbol, sig.action, sig.price,
                                   qty, sig.stop_loss, sig.target)

        # Log to order log for dashboard
        self._risk.order_log.append({
            "ts":     datetime.now().strftime("%H:%M:%S"),
            "symbol": sig.symbol, "action": sig.action,
            "price":  sig.price,  "qty":    qty,
            "type":   "ENTRY",    "oid":    oid,
        })
        if len(self._risk.order_log) > 100:
            self._risk.order_log = self._risk.order_log[-100:]

        for s in sig.strategies:
            if s in self._strat_stats: self._strat_stats[s]["signals"] += 1

    # ── Monitor ──────────────────────────────────────────────────────

    def _monitor(self):
        if not self._risk.positions: return
        syms = list(self._risk.positions.keys())
        ltps = {}
        if self._ws:
            for s in syms:
                tok = self._token_map.get(s)
                if tok:
                    ltp = self._ws.get_ltp_from_stream(tok)
                    if ltp and ltp > 0: ltps[s] = ltp
        missing = [s for s in syms if s not in ltps]
        if missing: ltps.update(self._md.get_ltp(missing))

        for sym in list(self._risk.positions.keys()):
            ltp = ltps.get(sym)
            if not ltp or ltp <= 0: continue
            pos = self._risk.positions.get(sym)
            if not pos: continue
            pos.current_price = ltp
            new_sl = self._risk.update_trailing_sl(pos, ltp)
            if abs(new_sl - pos.trailing_sl) > 0.01:
                pos.trailing_sl = new_sl
                try: self._orders.modify_gtt_sl(sym, new_sl, pos.target,
                                                 pos.entry_price, pos.quantity, pos.action)
                except Exception: pass
            reason = self._risk.check_exit(pos, ltp)
            if reason: self._close(sym, ltp, reason, pos)

    def _close(self, sym, ltp, reason, pos):
        try: self._orders.cancel_gtt(sym)
        except Exception: pass
        ea = "SELL" if pos.action=="BUY" else "BUY"
        if reason=="TARGET_HIT":
            self._orders.limit_order(sym, ea, pos.quantity, pos.target, "V7_TGT")
        else:
            self._orders.market_order(sym, ea, pos.quantity, "V7_SL")
        pnl = self._risk.close_position(sym, ltp, reason)
        self._notify.trade_closed(sym, pos.action, pos.entry_price,
                                   ltp, pos.quantity, pnl, reason)
        self._risk.order_log.append({
            "ts": datetime.now().strftime("%H:%M:%S"),
            "symbol": sym, "action": ea, "price": ltp, "qty": pos.quantity,
            "type": f"EXIT-{reason[:6]}", "oid": "",
        })
        for s in pos.strategy.split("+"):
            if s in self._strat_stats:
                k = "wins" if pnl>0 else "losses"
                self._strat_stats[s][k] = self._strat_stats[s].get(k,0)+1

    def _sq_all(self, reason="EOD"):
        logger.warning(f"Squaring off all [{reason}]...")
        try: self._orders.cleanup_all_gtts()
        except Exception: pass
        for pos in list(self._risk.positions.values()):
            ltp = self._md.get_ltp([pos.symbol]).get(pos.symbol, pos.current_price)
            ea = "SELL" if pos.action=="BUY" else "BUY"
            self._orders.market_order(pos.symbol, ea, pos.quantity, "V7_SQOFF")
            self._risk.close_position(pos.symbol, ltp, f"SQUARE_OFF_{reason}")

    def _coast(self):
        while self._running and now_ist() < cfg.SQUARE_OFF:
            self._monitor(); time.sleep(30)
        self._sq_all("EOD")

    def _in_market(self): return cfg.MARKET_OPEN <= now_ist() <= cfg.MARKET_CLOSE
    def _can_enter(self, t=None):
        t = t or now_ist()
        if not (cfg.ENTRY_START <= t < cfg.ENTRY_CUTOFF): return False
        if cfg.AVOID_LUNCH and cfg.LUNCH_START <= t <= cfg.LUNCH_END: return False
        return True
    def _stop_signal(self, *_): logger.info("Stop signal"); self._running = False

    def _shutdown(self):
        logger.info(f"\nFinal: P&L=₹{self._risk.total_pnl:+,.2f} "
                    f"Trades={self._risk.trade_count} WR={self._risk.win_rate:.1f}%")
        rp = ROOT/"reports"/f"report_{date.today()}.json"
        rp.parent.mkdir(exist_ok=True)
        rp.write_text(json.dumps({
            "date": str(date.today()), "pnl": round(self._risk.total_pnl,2),
            "trades": self._risk.trade_count, "win_rate": round(self._risk.win_rate,2),
            "wins": self._risk.win_count, "losses": self._risk.loss_count,
            "closed_trades": self._risk.closed_trades, "strategy_stats": self._strat_stats,
            "session": {"capital": self._session.capital,
                        "daily_target": self._session.daily_target,
                        "daily_loss_limit": self._session.daily_loss_limit},
        }, indent=2, default=str))
        self._indices.stop()
        if self._ws:
            try: self._ws.stop()
            except Exception: pass
        self._notify.bot_stopped(self._risk.total_pnl)

    def _banner(self):
        mode = "PAPER TRADING" if cfg.PAPER_TRADING else "LIVE — REAL MONEY"
        s = self._session
        print(f"""
╔════════════════════════════════════════════════════════════════════╗
║   KITE BOT v7.0 — PROFESSIONAL AUTO TRADING SYSTEM                ║
║   sourabhk1967@gmail.com                                           ║
╠════════════════════════════════════════════════════════════════════╣
║  Mode         : {mode:<51}║
║  Capital      : ₹{s.capital:<50,.0f}║
║  Daily Target : ₹{s.daily_target:<50,.0f}║
║  Max Loss/day : ₹{s.daily_loss_limit:<50,.0f}║
║  Stop Loss    : {s.stop_loss_pct}% per trade{' '*42}║
║  Risk/trade   : ₹{s.risk_per_trade:<50,.0f}║
║  Positions    : {s.max_positions} max{' '*48}║
║  Universe     : {len(cfg.WATCHLIST)} stocks — all major indices{' '*25}║
║  Dashboard    : http://127.0.0.1:{cfg.DASHBOARD_PORT}{' '*33}║
╠════════════════════════════════════════════════════════════════════╣
║  Change settings live at http://127.0.0.1:{cfg.DASHBOARD_PORT}/              ║
║  Auto-trades fire on multi-strategy consensus + ADX > 20           ║
╚════════════════════════════════════════════════════════════════════╝
""")


# ── CLI startup with parameter input ─────────────────────────────────

def ask_session() -> TradingSession:
    """Interactive CLI to set trading parameters at startup."""
    print("""
╔══════════════════════════════════════════════════════════╗
║   TRADING PARAMETERS SETUP                               ║
║   (Press Enter to use default values)                    ║
╚══════════════════════════════════════════════════════════╝
""")
    sess = TradingSession.load()

    def ask(prompt, current, cast=float):
        try:
            raw = input(f"  {prompt} [current: {current}]: ").strip()
            return cast(raw) if raw else current
        except Exception:
            return current

    sess.capital          = ask("Principal amount (₹)",   sess.capital)
    sess.daily_target     = ask("Daily profit target (₹)", sess.daily_target)
    sess.daily_loss_limit = ask("Max loss per day (₹)",    sess.daily_loss_limit)
    sess.stop_loss_pct    = ask("Stop loss % per trade",   sess.stop_loss_pct)
    sess.max_positions    = ask("Max positions",           sess.max_positions, int)
    sess.target_multiplier= ask("Target multiplier (SL×)", sess.target_multiplier)
    sess._recalculate()

    print(f"""
  Capital      : ₹{sess.capital:,.0f}
  Daily Target : ₹{sess.daily_target:,.0f}
  Max Loss     : ₹{sess.daily_loss_limit:,.0f}
  Stop Loss    : {sess.stop_loss_pct}%
  Max Positions: {sess.max_positions}
  Risk/trade   : ₹{sess.risk_per_trade:.0f}
  Target/trade : {sess.stop_loss_pct * sess.target_multiplier:.2f}% (₹{sess.risk_per_trade*sess.target_multiplier:.0f})
""")
    confirm = input("  Confirm? [Y/n]: ").strip().lower()
    if confirm == "n":
        return ask_session()
    sess.save()
    return sess


if __name__ == "__main__":
    sess = ask_session()
    set_session(sess)
    TradingBot(sess).run()
