"""Estrategia 1: trend following clásico sobre medias móviles.

Hipótesis: el oro tiene tendencias persistentes (flujos macro lentos:
bancos centrales, tipos reales, refugio). Seguirlas de forma mecánica
captura la parte central del movimiento renunciando a suelos y techos.

Reglas (deliberadamente simples — lo simple sobrevive mejor OOS):
  - LARGO  (+1) si el precio está por encima de su SMA rápida Y lenta.
  - CORTO  (-1) si está por debajo de ambas.
  - FUERA  (0)  si las señales discrepan (zona de ruido).

Usa las features sma_ratio_* ya calculadas (una fuente de verdad para
los indicadores; si un día cambia el cálculo, cambia en todas partes).
"""

from dataclasses import dataclass, field

import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class TrendFollowing(Strategy):
    name: str = "trend_following"
    description: str = "Largo sobre ambas SMAs (50/200), corto bajo ambas, fuera si discrepan"
    params: dict = field(default_factory=lambda: {"fast": 50, "slow": 200})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        fast = data.features[f"sma_ratio_{self.params['fast']}"]
        slow = data.features[f"sma_ratio_{self.params['slow']}"]
        long_signal = (fast > 0) & (slow > 0)
        short_signal = (fast < 0) & (slow < 0)
        positions = pd.Series(0.0, index=data.bars.index)
        positions[long_signal] = 1.0
        positions[short_signal] = -1.0
        # durante el calentamiento de la SMA lenta no hay señal válida
        positions[slow.isna()] = float("nan")
        return positions
