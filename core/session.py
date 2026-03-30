"""
core/session.py
===============
User Session Manager.

Stores the parameters entered by the user:
  • Principal (capital)
  • Per-day profit target
  • Stop-loss amount / percentage
  • Max positions

These override config defaults and are shared across all modules.
Can be set via CLI at startup OR via the dashboard control panel.
"""

import logging
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger("Session")

SESSION_FILE = Path(__file__).parent.parent / "config" / "session.json"


@dataclass
class TradingSession:
    # User-defined parameters
    capital:           float = 45_000.0   # Principal amount ₹
    daily_target:      float = 4_000.0    # Per-day profit target ₹
    daily_loss_limit:  float = 2_000.0    # Max loss before stopping ₹
    max_positions:     int   = 5          # Max simultaneous trades
    stop_loss_pct:     float = 1.0        # Stop loss % per trade
    target_multiplier: float = 2.5        # Target = SL × multiplier

    # Derived (auto-calculated)
    capital_per_trade: float = 0.0
    risk_per_trade:    float = 0.0        # ₹ at risk per trade
    mode:              str   = "PAPER"    # PAPER or LIVE

    def __post_init__(self):
        self._recalculate()

    def _recalculate(self):
        self.capital_per_trade = self.capital / max(self.max_positions, 1)
        self.risk_per_trade    = self.capital_per_trade * (self.stop_loss_pct / 100)

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self._recalculate()
        self.save()
        logger.info(
            f"Session updated: Capital=₹{self.capital:,.0f} "
            f"Target=₹{self.daily_target:,.0f} "
            f"MaxLoss=₹{self.daily_loss_limit:,.0f} "
            f"SL%={self.stop_loss_pct}% "
            f"Positions={self.max_positions}"
        )

    def apply_to_config(self, cfg):
        """Push session values into the live config module."""
        cfg.TOTAL_CAPITAL      = self.capital
        cfg.DAILY_TARGET       = self.daily_target
        cfg.DAILY_LOSS_LIMIT   = self.daily_loss_limit
        cfg.MAX_POSITIONS      = self.max_positions
        cfg.CAPITAL_PER_TRADE  = self.capital_per_trade
        cfg.MAX_RISK_PER_TRADE = self.stop_loss_pct / 100
        cfg.STOP_LOSS_PCT      = self.stop_loss_pct / 100
        cfg.TARGET_PCT         = (self.stop_loss_pct / 100) * self.target_multiplier
        cfg.PAPER_TRADING      = (self.mode == "PAPER")

    def save(self):
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps(asdict(self), indent=2))
        except Exception as e:
            logger.debug(f"Session save: {e}")

    @classmethod
    def load(cls) -> "TradingSession":
        try:
            if SESSION_FILE.exists():
                data = json.loads(SESSION_FILE.read_text())
                s = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
                s._recalculate()
                return s
        except Exception as e:
            logger.debug(f"Session load: {e}")
        return cls()

    def summary(self) -> str:
        return (
            f"Capital=₹{self.capital:,.0f} | "
            f"Target/day=₹{self.daily_target:,.0f} | "
            f"MaxLoss=₹{self.daily_loss_limit:,.0f} | "
            f"SL={self.stop_loss_pct}% | "
            f"Positions={self.max_positions} | "
            f"Risk/trade=₹{self.risk_per_trade:.0f} | "
            f"Mode={self.mode}"
        )


# Global session instance
_session: Optional[TradingSession] = None


def get_session() -> TradingSession:
    global _session
    if _session is None:
        _session = TradingSession.load()
    return _session


def set_session(sess: TradingSession):
    global _session
    _session = sess
