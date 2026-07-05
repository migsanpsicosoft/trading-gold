"""TSMomentum: time-series momentum 12-1 con rebalanceo mensual.

La especificación canónica de Moskowitz, Ooi & Pedersen (2012): el
signo del retorno de los últimos 12 meses (saltando el último, que
revierte) predice el mes siguiente. Documentado en 58 instrumentos de
4 clases de activo. Rebalanceo cada ~21 sesiones para el turnover de
la spec original (mensual).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class TSMomentum(Strategy):
    name: str = "ts_momentum"
    description: str = "Momentum 12-1 (MOP 2012): signo del retorno anual, rebalanceo mensual"
    params: dict = field(default_factory=lambda: {"lookback": 252, "skip": 21,
                                                  "rebalance": 21})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        close = data.bars["close"]
        p = self.params
        mom = close.shift(p["skip"]) / close.shift(p["lookback"]) - 1
        raw = pd.Series(np.sign(mom), index=close.index)
        # solo se decide en las fechas de rebalanceo; entre medias se mantiene
        is_rebalance = np.arange(len(close)) % p["rebalance"] == 0
        pos = raw.where(is_rebalance).ffill()
        pos[mom.isna()] = np.nan  # calentamiento del año de lookback
        return pos
