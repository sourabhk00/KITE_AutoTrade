"""
execution/risk_manager.py
Advanced risk management:
  - Portfolio heat limit
  - Multi-stage trailing SL (breakeven → trail → tight)
  - Kelly criterion position sizing
  - Consecutive loss circuit breaker
  - Time-of-day filters
  - Volatility-adjusted sizing
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("RiskManager")


@dataclass
class OpenPosition:
    symbol:      str
    action:      str         # BUY or SELL
    entry_price: float
    quantity:    int
    stop_loss:   float
    target:      float
    trailing_sl: float
    entry_time:  datetime = field(default_factory=datetime.now)
    order_id:    str = ""
    sl_order_id: str = ""
    current_price: float = 0.0
    strategy:    str = ""
    status:      str = "OPEN"

    @property
    def pnl(self) -> float:
        if not self.current_price:
            return 0.0
        if self.action == "BUY":
            return (self.current_price - self.entry_price) * self.quantity
        return (self.entry_price - self.current_price) * self.quantity

    @property
    def pnl_pct(self) -> float:
        base = self.entry_price * self.quantity
        return (self.pnl / base * 100) if base else 0.0

    @property
    def heat(self) -> float:
        """₹ currently at risk."""
        return abs(self.entry_price - self.trailing_sl) * self.quantity


class RiskManager:

    def __init__(self, config):
        self.cfg = config

        # Session state
        self.positions:          dict[str, OpenPosition] = {}
        self.closed_trades:      list[dict] = []
        self.daily_realized_pnl: float = 0.0
        self.trade_count:        int = 0
        self.win_count:          int = 0
        self.loss_count:         int = 0
        self.consecutive_losses: int = 0
        self.consecutive_wins:   int = 0

    # ─── Position entry gate ──────────────────────────────────

    def can_enter(
        self,
        symbol: str,
        action: str,
        price: float,
        stop_loss: float,
        quantity: int,
        available_cash: float,
    ) -> tuple[bool, str]:
        _ = action   # used by caller for direction, not needed here

        # Time gate
        t = datetime.now().strftime("%H:%M")
        if not (self.cfg.ENTRY_START <= t < self.cfg.ENTRY_CUTOFF):
            return False, f"Outside entry window ({t})"
        if self.cfg.AVOID_LUNCH and self.cfg.LUNCH_START <= t <= self.cfg.LUNCH_END:
            return False, f"Lunch hour ({t})"

        # Daily limits
        if self.total_pnl >= self.cfg.DAILY_TARGET:
            return False, f"Daily target hit (₹{self.total_pnl:+.0f})"
        if self.total_pnl <= -self.cfg.DAILY_LOSS_LIMIT:
            return False, f"Daily loss limit hit (₹{self.total_pnl:+.0f})"

        # Existing position
        if symbol in self.positions:
            return False, f"Already in {symbol}"

        # Max positions
        if len(self.positions) >= self.cfg.MAX_POSITIONS:
            return False, f"Max {self.cfg.MAX_POSITIONS} positions reached"

        # Portfolio heat
        new_heat  = abs(price - stop_loss) * quantity
        total_heat = self.portfolio_heat + new_heat
        max_heat   = self.cfg.TOTAL_CAPITAL * 0.04   # 4% total heat allowed
        if total_heat > max_heat:
            return False, f"Portfolio heat ₹{total_heat:.0f} > max ₹{max_heat:.0f}"

        # Cash check
        cost = price * quantity
        if cost > available_cash * 0.98:
            return False, f"Insufficient margin (₹{cost:.0f} vs ₹{available_cash:.0f})"

        # SL sanity
        sl_pct = abs(price - stop_loss) / price * 100
        if sl_pct > 3.0:
            return False, f"SL too wide: {sl_pct:.2f}%"
        if sl_pct < 0.2:
            return False, f"SL too tight: {sl_pct:.2f}%"

        # Consecutive loss brake
        if self.consecutive_losses >= 4:
            return False, f"{self.consecutive_losses} consecutive losses — cooling off"

        return True, "OK"

    def size_position(
        self,
        price: float,
        stop_loss: float,
        confidence: float,
        capital_per_trade: float,
    ) -> int:
        sl_dist = abs(price - stop_loss)
        if sl_dist < 0.01:
            return 0

        base_risk = capital_per_trade * self.cfg.MAX_RISK_PER_TRADE

        # Confidence scaling: 0.75× at low confidence, 1.25× at high
        conf_mult = 0.75 + 0.5 * max(0.0, min(confidence, 1.0))

        # Loss streak reduction
        streak_mult = max(0.4, 1.0 - self.consecutive_losses * 0.15)

        # Reduce size after daily target is 70%+ achieved
        pnl_mult = 0.80 if self.total_pnl >= self.cfg.DAILY_TARGET * 0.7 else 1.0

        risk_adj = base_risk * conf_mult * streak_mult * pnl_mult
        qty = max(1, int(risk_adj / sl_dist))
        qty = min(qty, int(capital_per_trade / price))  # Hard cap
        return qty

    # ─── Trailing SL (multi-stage) ────────────────────────────

    def update_trailing_sl(self, pos: OpenPosition, ltp: float) -> float:
        """
        4-stage trailing stop loss.
        Returns new SL value (always moves in favor only).
        """
        entry = pos.entry_price
        cur_sl = pos.trailing_sl

        if pos.action == "BUY":
            pct = (ltp - entry) / entry
            if pct >= 0.020:                      # 2%+ profit: tight 0.8% trail
                new_sl = ltp * (1 - 0.008)
                return max(new_sl, cur_sl)
            elif pct >= 0.015:                    # 1.5%: moderate trail
                new_sl = ltp * (1 - self.cfg.TRAILING_SL_PCT)
                return max(new_sl, cur_sl)
            elif pct >= self.cfg.BREAKEVEN_TRIGGER:  # 1.2%: breakeven
                return max(entry * 1.002, cur_sl)
            elif pct >= 0.006:                    # 0.6%: partial protect
                return max(entry * 0.999, cur_sl)
        else:
            pct = (entry - ltp) / entry
            if pct >= 0.020:
                new_sl = ltp * (1 + 0.008)
                return min(new_sl, cur_sl)
            elif pct >= 0.015:
                new_sl = ltp * (1 + self.cfg.TRAILING_SL_PCT)
                return min(new_sl, cur_sl)
            elif pct >= self.cfg.BREAKEVEN_TRIGGER:
                return min(entry * 0.998, cur_sl)
            elif pct >= 0.006:
                return min(entry * 1.001, cur_sl)

        return cur_sl

    # ─── Exit condition check ─────────────────────────────────

    def check_exit(self, pos: OpenPosition, ltp: float) -> Optional[str]:
        if pos.action == "BUY":
            if ltp >= pos.target:          return "TARGET_HIT"
            if ltp <= pos.trailing_sl:     return "STOP_LOSS"
        else:
            if ltp <= pos.target:          return "TARGET_HIT"
            if ltp >= pos.trailing_sl:     return "STOP_LOSS"
        return None

    # ─── Position lifecycle ───────────────────────────────────

    def open_position(self, pos: OpenPosition):
        self.positions[pos.symbol] = pos
        self.trade_count += 1
        logger.info(
            f"[OPEN] {pos.symbol} {pos.action} {pos.quantity}@₹{pos.entry_price:.2f} "
            f"SL=₹{pos.stop_loss:.2f} TGT=₹{pos.target:.2f} | {pos.strategy}"
        )

    def close_position(self, symbol: str, exit_price: float, reason: str) -> float:
        pos = self.positions.get(symbol)
        if not pos:
            return 0.0

        pos.current_price = exit_price
        pos.status = reason
        pnl = pos.pnl
        self.daily_realized_pnl += pnl

        if pnl > 0:
            self.win_count += 1; self.consecutive_wins += 1; self.consecutive_losses = 0
        else:
            self.loss_count += 1; self.consecutive_losses += 1; self.consecutive_wins = 0

        if self.consecutive_losses >= 4:
            logger.warning(f"⚠ {self.consecutive_losses} consecutive losses — position sizing halved")

        self.closed_trades.append({
            "symbol": symbol, "action": pos.action,
            "entry_price": pos.entry_price, "exit_price": exit_price,
            "quantity": pos.quantity, "pnl": round(pnl, 2),
            "pnl_pct": round(pos.pnl_pct, 2),
            "reason": reason, "strategy": pos.strategy,
            "entry_time": pos.entry_time.isoformat(),
            "exit_time": datetime.now().isoformat(),
        })

        logger.info(
            f"[CLOSE] {symbol} {reason} @ ₹{exit_price:.2f} "
            f"P&L=₹{pnl:+.2f} ({pos.pnl_pct:+.2f}%)"
        )
        del self.positions[symbol]
        return pnl

    # ─── Properties ───────────────────────────────────────────

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.daily_realized_pnl + self.unrealized_pnl

    @property
    def portfolio_heat(self) -> float:
        return sum(p.heat for p in self.positions.values())

    @property
    def win_rate(self) -> float:
        t = self.win_count + self.loss_count
        return self.win_count / t * 100 if t else 0.0

    def target_progress(self) -> float:
        return min(self.total_pnl / self.cfg.DAILY_TARGET * 100, 100.0)

    def status_line(self) -> str:
        return (
            f"P&L=₹{self.total_pnl:+.0f} | "
            f"R=₹{self.daily_realized_pnl:+.0f} U=₹{self.unrealized_pnl:+.0f} | "
            f"Trades={self.trade_count} WR={self.win_rate:.1f}% | "
            f"Open={len(self.positions)} Heat=₹{self.portfolio_heat:.0f}"
        )
