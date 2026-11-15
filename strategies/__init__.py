"""선택 가능한 매매법 목록."""
from .base import HORIZONS, Panel, Param, Result, Strategy
from .reversal import BollingerRebound, MacdCross, RsiRebound
from .trend import GoldenCross, High52, Momentum, TurtleBreakout
from .volume import VolumeSurge

ALL_STRATEGIES: list[Strategy] = [
    GoldenCross(), Momentum(), TurtleBreakout(), High52(),
    RsiRebound(), BollingerRebound(), MacdCross(),
    VolumeSurge(),
]
BY_KEY = {s.key: s for s in ALL_STRATEGIES}

__all__ = ["ALL_STRATEGIES", "BY_KEY", "HORIZONS", "Panel", "Param", "Result", "Strategy"]
