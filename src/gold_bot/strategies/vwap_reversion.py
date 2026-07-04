"""Estrategia 7: reversión al VWAP intradía.

El VWAP (precio medio ponderado por volumen del día) es la referencia
de ejecución institucional: los algos de las mesas grandes trabajan
órdenes "pegadas al VWAP". Hipótesis: cuando el precio se estira mucho
respecto al VWAP sin motivo direccional, ese flujo institucional lo
atrae de vuelta.

Reglas (por día, sobre barras de 15m UTC):
  - Desviación dev = (precio − VWAP) / VWAP.
  - Banda = m × desviación típica móvil de dev en los últimos
    `band_window` barras (≈5 días), con shift(1).
  - LARGO si dev < −banda (estirado por debajo); CORTO si dev > +banda.
  - SALIDA cuando dev cruza 0 (el precio volvió al VWAP).
  - Última barra del día: posición 0 SIEMPRE (planas overnight).

Nota: el volumen es tick volume (nº de cambios de precio), no volumen
negociado — en OTC no existe el real. Como ponderador relativo del
VWAP funciona bien (las horas activas pesan más).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import IntradayData, IntradayStrategy


@dataclass
class VwapReversion(IntradayStrategy):
    name: str = "vwap_reversion"
    description: str = "Estirones vs VWAP del día a ±2σ móviles; sale en el VWAP, plana overnight"
    params: dict = field(default_factory=lambda: {"entry_m": 2.0, "band_window": 480})

    def generate_positions(self, data: IntradayData) -> pd.Series:
        b = data.bars15
        m, w = self.params["entry_m"], self.params["band_window"]
        days = b.index.normalize()

        vol = b["volume"].fillna(0.0)
        pv = (b["close"] * vol).groupby(days).cumsum()
        cum_vol = vol.groupby(days).cumsum()
        vwap = (pv / cum_vol).replace([np.inf, -np.inf], np.nan)

        dev = ((b["close"] - vwap) / vwap).to_numpy()
        band = (pd.Series(dev, index=b.index).rolling(w).std().shift(1) * m).to_numpy()

        day_arr = days.to_numpy()
        is_last = np.r_[day_arr[:-1] != day_arr[1:], True]

        pos = np.full(len(dev), np.nan)
        state = 0.0
        prev_day = None
        for i in range(len(dev)):
            if day_arr[i] != prev_day:
                prev_day = day_arr[i]
                state = 0.0
            if np.isnan(dev[i]) or np.isnan(band[i]):
                continue
            if state == 0.0:
                if dev[i] < -band[i]:
                    state = 1.0
                elif dev[i] > band[i]:
                    state = -1.0
            elif (state == 1.0 and dev[i] >= 0) or (state == -1.0 and dev[i] <= 0):
                state = 0.0  # volvió al VWAP
            pos[i] = 0.0 if is_last[i] else state
        return pd.Series(pos, index=b.index)
