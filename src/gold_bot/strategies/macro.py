"""Estrategia 5: posicionamiento por drivers macro del oro.

Los dos motores estructurales del precio del oro:

  1. TIPOS REALES: el oro no paga cupón; su coste de oportunidad es el
     tipo real. TIP (ETF de bonos ligados a inflación) SUBE cuando los
     tipos reales BAJAN → TIP con momentum positivo es alcista para
     el oro.
  2. DÓLAR: el oro cotiza en USD; dólar fuerte = oro caro para el
     resto del mundo → DXY con momentum positivo es bajista.

Cada driver vota ±0.5 según su momentum de 20 días; la posición es la
suma de votos ∈ {-1, 0, +1}. Cuando los drivers discrepan la posición
neta es 0 — la versión con votos ponderados la aprenderá el meta-modelo
(Fase 4), no la cableamos a mano.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class Macro(Strategy):
    name: str = "macro"
    description: str = "Votos ±0.5 de tipos reales (TIP) y dólar (DXY) por momentum 20d"
    params: dict = field(default_factory=lambda: {"lookback": 20})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        tip = data.features["tip_ret_20d"]
        dxy = data.features["dxy_ret_20d"]
        tip_vote = np.where(tip > 0, 0.5, -0.5)   # tipos reales bajando → alcista
        dxy_vote = np.where(dxy < 0, 0.5, -0.5)   # dólar debilitándose → alcista
        pos = pd.Series(tip_vote + dxy_vote, index=data.bars.index)
        pos[tip.isna() | dxy.isna()] = np.nan     # calentamiento de los momentum
        return pos
