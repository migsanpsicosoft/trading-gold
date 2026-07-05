"""OvernightEquity: el retorno del índice se gana durmiendo.

Documentado desde Lou/Polk/Skouras y vigente en 2024-25: el retorno de
los índices de renta variable se concentra en el tramo cierre→apertura;
el intradía es ~ruido. EXCEPCIÓN DELIBERADA al contrato plana-overnight
de las estrategias intradía: aquí la hipótesis ES el salto nocturno.

Implementación: posición +1 SOLO en la última barra del día → el
shift(1) del motor la hace ganar la primera barra del día siguiente
(gap nocturno incluido) y se sale inmediatamente después.

Riesgo conocido y pre-declarado: 2 cruces de spread al día (~2 pb en
SPX). Los ETFs NightShares murieron por esto en 2023. La criba de
costes decide — si no sobrevive al spread, muere con honores.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import IntradayData, IntradayStrategy


@dataclass
class OvernightEquity(IntradayStrategy):
    name: str = "overnight_equity"
    description: str = "Largo solo el tramo nocturno (última barra → primera del día siguiente)"
    params: dict = field(default_factory=dict)

    def generate_positions(self, data: IntradayData) -> pd.Series:
        b = data.bars15
        day = b.index.normalize().to_numpy()
        is_last = np.r_[day[:-1] != day[1:], True]
        pos = pd.Series(0.0, index=b.index)
        pos[is_last] = 1.0
        return pos
