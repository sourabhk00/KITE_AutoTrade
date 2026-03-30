"""
utils/notifier.py
Send alerts via Telegram and desktop notifications.
"""

import logging
import requests
from datetime import datetime

logger = logging.getLogger("Notifier")


class Notifier:
    def __init__(self, config):
        self.cfg = config
        self.tg_ok = False
        token = getattr(config, "TELEGRAM_TOKEN", "")
        if token:
            try:
                r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=4)
                self.tg_ok = r.status_code == 200
                if self.tg_ok:
                    logger.info("Telegram alerts enabled")
            except Exception:
                pass

    def _tg(self, text: str):
        if not self.tg_ok:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.cfg.TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": self.cfg.TELEGRAM_CHAT_ID,
                      "text": text, "parse_mode": "Markdown"},
                timeout=5,
            )
        except Exception:
            pass

    def _desktop(self, title: str, msg: str):
        try:
            from plyer import notification
            notification.notify(title=title, message=msg, timeout=6)
        except Exception:
            pass

    def trade_opened(self, sym, action, price, qty, sl, tgt):
        icon = "🟢" if action == "BUY" else "🔴"
        msg = (f"{icon} *{action} {sym}*\n"
               f"Entry: ₹{price:.2f} | Qty: {qty}\n"
               f"SL: ₹{sl:.2f} | TGT: ₹{tgt:.2f}")
        logger.info(f"{icon} {action} {qty} {sym} @ ₹{price:.2f}")
        self._tg(msg)
        self._desktop(f"{action} {sym}", f"₹{price:.2f} SL={sl:.2f} TGT={tgt:.2f}")

    def trade_closed(self, sym, action, entry, exit_p, qty, pnl, reason):
        icon = "✅" if pnl > 0 else "❌"
        msg = (f"{icon} *CLOSED {sym}*\n"
               f"₹{entry:.2f} → ₹{exit_p:.2f} | Qty: {qty}\n"
               f"P&L: *₹{pnl:+.2f}* | {reason}")
        logger.info(f"{icon} CLOSED {sym} P&L=₹{pnl:+.2f} [{reason}]")
        self._tg(msg)
        self._desktop(f"Closed {sym}", f"P&L ₹{pnl:+.2f} [{reason}]")

    def daily_target(self, pnl):
        msg = f"🏆 *Daily target hit!*\nP&L: ₹{pnl:+.2f}"
        logger.info(f"🏆 Daily target hit: ₹{pnl:+.2f}")
        self._tg(msg); self._desktop("Target Hit!", f"₹{pnl:+.2f}")

    def daily_loss_limit(self, pnl):
        msg = f"🛑 *Loss limit hit — trading stopped*\nP&L: ₹{pnl:+.2f}"
        logger.warning(f"🛑 Loss limit hit: ₹{pnl:+.2f}")
        self._tg(msg); self._desktop("Loss Limit Hit", f"₹{pnl:+.2f}")

    def bot_started(self, paper: bool):
        mode = "PAPER" if paper else "LIVE"
        msg  = f"🚀 *Bot started [{mode}]*\nCapital: ₹{self.cfg.TOTAL_CAPITAL:,}"
        self._tg(msg)

    def bot_stopped(self, pnl: float):
        msg = f"🔴 *Bot stopped* | Final P&L: ₹{pnl:+.2f}"
        self._tg(msg)
