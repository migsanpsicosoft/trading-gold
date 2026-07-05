"""MonthlySeasonality: estacionalidad mensual adaptativa.

Los commodities tienen ciclos anuales documentados (gas natural:
inyección en verano, extracción en invierno). Como con las sesiones
del oro: NO se cablea "compra agosto" — la deriva de cada mes natural
se estima con sus ocurrencias de años ANTERIORES y solo se opera si
el t-stat supera el umbral. Si el patrón muere, se apaga solo.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class MonthlySeasonality(Strategy):
    name: str = "monthly_seasonality"
    description: str = "Opera el mes natural solo si su deriva histórica es significativa (|t|>1.5)"
    params: dict = field(default_factory=lambda: {"lookback_years": 6,
                                                  "t_threshold": 1.5,
                                                  "min_years": 4})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        ret = data.features["ret_1d"]
        idx = data.bars.index
        p = self.params

        frame = pd.DataFrame({"y": idx.year, "m": idx.month, "r": ret.to_numpy()},
                             index=idx)
        # retorno medio diario de cada (año, mes) → tabla año × mes
        occurrences = frame.groupby(["y", "m"])["r"].mean().unstack("m")

        # deriva del mes m en el año y: SOLO con años anteriores (shift)
        mean = occurrences.rolling(p["lookback_years"],
                                   min_periods=p["min_years"]).mean().shift(1)
        std = occurrences.rolling(p["lookback_years"],
                                  min_periods=p["min_years"]).std().shift(1)
        count = occurrences.rolling(p["lookback_years"],
                                    min_periods=p["min_years"]).count().shift(1)
        tstat = mean / (std / np.sqrt(count))

        signal = pd.DataFrame(
            np.where(tstat > p["t_threshold"], 1.0,
                     np.where(tstat < -p["t_threshold"], -1.0, 0.0)),
            index=tstat.index, columns=tstat.columns,
        )
        signal[mean.isna()] = np.nan

        keys = pd.MultiIndex.from_arrays([idx.year, idx.month])
        pos = signal.stack().reindex(keys).to_numpy()
        return pd.Series(pos, index=idx)
