"""Estrategia 3: reversión a la media con bandas de Bollinger.

Hipótesis: los estirones violentos del oro respecto a su media de
corto plazo (pánico, liquidaciones, squeezes) tienden a deshacerse
en días. Es la apuesta CONTRARIA al breakout — de ahí que ambas
deberían estar descorrelacionadas (diversificación real).

Reglas sobre el z-score del cierre vs su SMA de `window` días:
  - LARGO si z < -entry_z (precio estirado por debajo).
  - CORTO si z > +entry_z (estirado por encima).
  - SALIDA cuando z cruza 0 (el precio volvió a su media).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class MeanReversion(Strategy):
    name: str = "mean_reversion"
    description: str = "Bollinger z-score 20d: entra a ±2σ contra el estirón, sale en la media"
    params: dict = field(default_factory=lambda: {"window": 20, "entry_z": 2.0})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        close = data.bars["close"]
        w, entry_z = self.params["window"], self.params["entry_z"]
        sma = close.rolling(w).mean()
        std = close.rolling(w).std()
        z = ((close - sma) / std).to_numpy()

        pos = np.full(len(z), np.nan)
        state = 0.0
        for i in range(len(z)):
            if np.isnan(z[i]):
                continue
            if state == 0.0:
                if z[i] < -entry_z:
                    state = 1.0
                elif z[i] > entry_z:
                    state = -1.0
            elif (state == 1.0 and z[i] >= 0) or (state == -1.0 and z[i] <= 0):
                state = 0.0  # el precio volvió a su media
            pos[i] = state
        return pd.Series(pos, index=close.index)
