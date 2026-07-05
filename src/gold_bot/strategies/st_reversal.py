"""ShortTermReversal: reversión semanal con posición continua.

El retorno de ~5 días tiende a revertir parcialmente (efecto de
microestructura y sobre-reacción, documentado cross-asset). Posición
continua proporcional al estirón normalizado, con clip — el turnover
es suave (la posición cambia gradualmente, no a saltos).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData

TRADING_DAYS = 252


@dataclass
class ShortTermReversal(Strategy):
    name: str = "st_reversal"
    description: str = "Reversión del retorno 5d normalizado por vol; posición continua"
    params: dict = field(default_factory=lambda: {"horizon": 5, "scale": 2.0})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        f = data.features
        vol_h = f["vol_20d"] / np.sqrt(TRADING_DAYS) * np.sqrt(self.params["horizon"])
        z = f["ret_5d"] / vol_h
        pos = (-z / self.params["scale"]).clip(-1.0, 1.0)
        pos[f["ret_5d"].isna() | f["vol_20d"].isna()] = np.nan
        return pd.Series(pos, index=data.bars.index)
