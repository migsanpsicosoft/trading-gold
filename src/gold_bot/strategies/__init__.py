"""Estrategias base: cada una emite posiciones objetivo en [-1, +1].

El registro STRATEGIES es la fuente de verdad de qué estrategias
existen; la API y el backtest iteran sobre él.
"""

from gold_bot.strategies.base import Strategy, StrategyData
from gold_bot.strategies.breakout import Breakout
from gold_bot.strategies.mean_reversion import MeanReversion
from gold_bot.strategies.trend_following import TrendFollowing

STRATEGIES: dict[str, Strategy] = {
    s.name: s
    for s in [
        TrendFollowing(),
        Breakout(),
        MeanReversion(),
    ]
}

__all__ = ["STRATEGIES", "Strategy", "StrategyData"]
