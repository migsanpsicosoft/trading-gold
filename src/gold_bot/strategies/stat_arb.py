"""Estrategia 4: stat arb sobre el ratio oro/plata.

Hipótesis: oro y plata comparten drivers monetarios; su ratio oscila
alrededor de una norma lenta. Estirones extremos del ratio tienden a
converger (la plata sobre-reacciona en ambas direcciones).

Reglas sobre xau_xag_z60 (z-score móvil 60d del ratio, de features):
  - CORTO oro si z > entry_z  (oro caro vs plata → apostar convergencia).
  - LARGO oro si z < -entry_z (oro barato vs plata).
  - SALIDA cuando z cruza 0.

Nota: el stat arb canónico opera ambas patas (corto oro + largo plata)
para aislar el spread. Aquí operamos solo la pata del oro — el
framework es mono-activo hasta la Fase 7. Misma señal, más volatilidad
residual (nos queda la beta direccional del oro durante el trade).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class StatArbXauXag(Strategy):
    name: str = "stat_arb_xau_xag"
    description: str = "Ratio oro/plata a ±2σ (z móvil 60d): apuesta a la convergencia, sale en 0"
    params: dict = field(default_factory=lambda: {"entry_z": 2.0})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        z = data.features["xau_xag_z60"].to_numpy()
        entry = self.params["entry_z"]
        pos = np.full(len(z), np.nan)
        state = 0.0
        for i in range(len(z)):
            if np.isnan(z[i]):
                continue
            if state == 0.0:
                if z[i] > entry:
                    state = -1.0  # oro caro vs plata → corto oro
                elif z[i] < -entry:
                    state = 1.0
            elif (state == -1.0 and z[i] <= 0) or (state == 1.0 and z[i] >= 0):
                state = 0.0  # el ratio volvió a su norma
            pos[i] = state
        return pd.Series(pos, index=data.bars.index)
