"""cot_extreme: contrarian en extremos de posicionamiento especulativo.

Cuando los no-comerciales (especuladores) están posicionados en un
extremo histórico, el movimiento está "lleno": el último comprador ya
compró y la reversión es más probable que la continuación (documentado
en FX y commodities). El COT llega con su lag de publicación ya
aplicado en la feature cot_z (ver data/cot.py).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class CotExtreme(Strategy):
    name: str = "cot_extreme"
    description: str = "Contrarian cuando el posicionamiento espec. está a ±2σ; sale en ±0.5σ"
    params: dict = field(default_factory=lambda: {"entry_z": 2.0, "exit_z": 0.5})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        z = data.features["cot_z"].to_numpy()
        entry, exit_ = self.params["entry_z"], self.params["exit_z"]
        pos = np.full(len(z), np.nan)
        state = 0.0
        for i in range(len(z)):
            if np.isnan(z[i]):
                continue
            if state == 0.0:
                if z[i] > entry:
                    state = -1.0  # especuladores saturados de largos → corto
                elif z[i] < -entry:
                    state = 1.0
            elif abs(z[i]) < exit_:
                state = 0.0  # el posicionamiento volvió a la normalidad
            pos[i] = state
        return pd.Series(pos, index=data.bars.index)
