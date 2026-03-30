"""
strategies/base.py
Abstract base class for all trading strategies.
Extend this to create custom strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from strategies.indicator_bundle import IndicatorSnapshot


@dataclass
class StrategyResult:
    score: float      # -1.0 (strong sell) to +1.0 (strong buy)
    reason: str = ""


class BaseStrategy(ABC):
    """
    All strategies inherit from this.
    Implement run() to return a StrategyResult.
    """

    name: str = "BASE"
    weight: float = 1.0

    def __init__(self, config):
        self.cfg = config

    @abstractmethod
    def run(self, snap: IndicatorSnapshot, **kwargs) -> Optional[StrategyResult]:
        """
        Analyse indicator snapshot and return a score.
        Return None to abstain (neither buy nor sell).
        """
        ...

    def __repr__(self):
        return f"<Strategy: {self.name} weight={self.weight}>"
