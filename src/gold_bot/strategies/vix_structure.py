"""vix_structure: la estructura temporal del VIX como semáforo de equity.

En calma el VIX está en contango (VIX3M > VIX): la prima de riesgo se
cobra estando largo. En estrés se invierte (backwardation): el mercado
paga por protección inmediata — históricamente el peor momento para
estar largo. Documentado como señal de timing de renta variable.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class VixStructure(Strategy):
    name: str = "vix_structure"
    description: str = "Largo SPX en contango del VIX, corto en backwardation; banda ±2%"
    params: dict = field(default_factory=lambda: {"deadband": 0.02})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        ratio = data.features["vix_ratio"]
        band = self.params["deadband"]
        pos = pd.Series(
            np.where(ratio > band, 1.0, np.where(ratio < -band, -1.0, 0.0)),
            index=data.bars.index,
        )
        pos[ratio.isna()] = np.nan
        return pos
