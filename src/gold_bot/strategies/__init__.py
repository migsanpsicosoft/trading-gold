"""Estrategias base: cada una emite posiciones objetivo en [-1, +1].

Dos registros: STRATEGIES (diarias) e INTRADAY_STRATEGIES (barras 15m,
planas overnight). La API y los backtests iteran sobre ellos.
"""

from gold_bot.strategies.base import (
    IntradayData,
    IntradayStrategy,
    Strategy,
    StrategyData,
)
from gold_bot.strategies.breakout import Breakout
from gold_bot.strategies.macro import Macro
from gold_bot.strategies.mean_reversion import MeanReversion
from gold_bot.strategies.session_seasonality import SessionSeasonality
from gold_bot.strategies.stat_arb import StatArbXauXag
from gold_bot.strategies.trend_following import TrendFollowing
from gold_bot.strategies.vol_breakout import VolBreakout
from gold_bot.strategies.vwap_reversion import VwapReversion

STRATEGIES: dict[str, Strategy] = {
    s.name: s
    for s in [
        TrendFollowing(),
        Breakout(),
        MeanReversion(),
        StatArbXauXag(),
        Macro(),
    ]
}

INTRADAY_STRATEGIES: dict[str, IntradayStrategy] = {
    s.name: s
    for s in [
        VolBreakout(),
        VwapReversion(),
        SessionSeasonality(),
    ]
}

__all__ = [
    "INTRADAY_STRATEGIES",
    "STRATEGIES",
    "IntradayData",
    "IntradayStrategy",
    "Strategy",
    "StrategyData",
]
