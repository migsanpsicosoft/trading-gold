"""Estrategias de carry: el factor documentado nº1 fuera del momentum.

- FxCarry (EUR, JPY): largo la divisa de tipo alto (Lustig-Verdelhan).
  La feature carry_diff ya viene orientada al activo: positiva = largo.
- CurveCarry (USB): pendiente 10a-2a positiva = carry + rolldown de
  estar largo duración; curva invertida → corto.

Ambas con banda muerta: sin señal cuando la diferencia es ruido.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


def _deadband_sign(series: pd.Series, band: float, index) -> pd.Series:
    pos = pd.Series(
        np.where(series > band, 1.0, np.where(series < -band, -1.0, 0.0)),
        index=index,
    )
    pos[series.isna()] = np.nan
    return pos


@dataclass
class FxCarry(Strategy):
    name: str = "fx_carry"
    description: str = "Largo la divisa de tipo alto (carry); banda muerta 0.25 pp"
    params: dict = field(default_factory=lambda: {"deadband": 0.25})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        return _deadband_sign(data.features["carry_diff"],
                              self.params["deadband"], data.bars.index)


@dataclass
class CurveCarry(Strategy):
    name: str = "curve_carry"
    description: str = "Largo duración con curva positiva, corto con inversión; banda 0.10 pp"
    params: dict = field(default_factory=lambda: {"deadband": 0.10})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        return _deadband_sign(data.features["curve_slope"],
                              self.params["deadband"], data.bars.index)
