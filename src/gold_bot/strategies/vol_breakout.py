"""Estrategia 6: volatility breakout intradía (opening range breakout).

Hipótesis: cuando el oro se mueve desde la apertura del día más de lo
que suele moverse en un día ENTERO normal, algo está pasando (dato
macro, flujo forzado) y el movimiento tiende a continuar hasta el
cierre. Es momentum intradía condicionado a volatilidad anormal.

Reglas (por día, sobre barras de 15m UTC):
  - Umbral: apertura del día ± k × rango medio diario de los últimos
    `range_window` días (rango de días ANTERIORES — shift(1)).
  - LARGO si el cierre de una barra supera el umbral superior;
    CORTO si pierde el inferior. Una entrada por día, se mantiene
    hasta el cierre.
  - Última barra del día: posición 0 SIEMPRE (planas overnight).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import IntradayData, IntradayStrategy


@dataclass
class VolBreakout(IntradayStrategy):
    name: str = "vol_breakout"
    description: str = "Ruptura de apertura ± k·rango medio 14d; hasta el cierre, plana overnight"
    params: dict = field(default_factory=lambda: {"k": 0.5, "range_window": 14})

    def generate_positions(self, data: IntradayData) -> pd.Series:
        b = data.bars15
        k, w = self.params["k"], self.params["range_window"]
        days = b.index.normalize()

        day_open = b["open"].groupby(days).transform("first")
        # rango medio de los w días ANTERIORES, mapeado a cada barra
        daily_range = b["high"].groupby(days).max() - b["low"].groupby(days).min()
        range_ref = daily_range.rolling(w).mean().shift(1)
        ref = range_ref.reindex(days).to_numpy()

        c = b["close"].to_numpy()
        up = day_open.to_numpy() + k * ref
        dn = day_open.to_numpy() - k * ref
        day_arr = days.to_numpy()
        is_last = np.r_[day_arr[:-1] != day_arr[1:], True]  # última barra de cada día

        pos = np.full(len(c), np.nan)
        state = 0.0
        prev_day = None
        for i in range(len(c)):
            if day_arr[i] != prev_day:
                prev_day = day_arr[i]
                state = 0.0  # cada día empieza plano
            if np.isnan(ref[i]):
                continue  # calentamiento del rango de referencia
            if state == 0.0:
                if c[i] > up[i]:
                    state = 1.0
                elif c[i] < dn[i]:
                    state = -1.0
            pos[i] = 0.0 if is_last[i] else state  # plana al cierre del día
        return pd.Series(pos, index=b.index)
