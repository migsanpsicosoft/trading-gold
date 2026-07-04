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

# Criba Fase 2 (2026-07-04, aprobada por Miguel): vwap_reversion descartada
# (Sharpe OOS bruto -0.85: sin edge que rescatar). El código queda en
# vwap_reversion.py como referencia. stat_arb y session_seasonality en
# observación hasta después del meta-modelo (F4).
INTRADAY_STRATEGIES: dict[str, IntradayStrategy] = {
    s.name: s
    for s in [
        VolBreakout(),
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
