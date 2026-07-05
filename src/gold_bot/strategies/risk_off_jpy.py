"""RiskOffJPY: el yen como divisa refugio.

Documentado (Ranaldo & Söderlind): en episodios risk-off el yen se
aprecia (repatriación de carry trades, demanda de refugio). Señal:
posición en USD/JPY = signo del momentum de 60 días del S&P 500 —
equities subiendo (risk-on) → largo USDJPY; cayendo → corto.

Requiere la feature cross-asset spx_ret_60d, que el libro de JPY
inyecta en sus features (multi_asset._extra_features).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class RiskOffJPY(Strategy):
    name: str = "risk_off_jpy"
    description: str = "USD/JPY = signo del momentum 60d del S&P (yen refugio en risk-off)"
    params: dict = field(default_factory=lambda: {"lookback": 60})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        spx_mom = data.features["spx_ret_60d"]
        pos = pd.Series(np.sign(spx_mom), index=data.bars.index)
        pos[spx_mom.isna()] = np.nan
        return pos
