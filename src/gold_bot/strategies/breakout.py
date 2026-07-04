"""Estrategia 2: breakout de canal Donchian (estilo 'turtle traders').

Hipótesis: cuando el oro rompe el rango de las últimas ~11 semanas,
suele ser el inicio de un movimiento mayor (entran flujos que tardan
en completarse). Complementa al trend following: entra ANTES (en la
ruptura) en vez de esperar a que las medias confirmen.

Reglas:
  - LARGO si el cierre supera el máximo de los `entry` días ANTERIORES.
  - CORTO si pierde el mínimo de los `entry` días anteriores.
  - SALIDA al tocar el extremo opuesto de `exit` días (más cercano →
    recorta antes las pérdidas que la entrada opuesta).

Anti-leakage: el canal usa .shift(1) — el máximo de los N días
anteriores SIN incluir hoy. Comparar el cierre de hoy contra un canal
que incluye hoy hace imposible romper el canal (autocomparación).
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import Strategy, StrategyData


@dataclass
class Breakout(Strategy):
    name: str = "breakout"
    description: str = "Donchian 55/20: entra en la ruptura del canal, sale en el extremo opuesto"
    params: dict = field(default_factory=lambda: {"entry": 55, "exit": 20})

    def generate_positions(self, data: StrategyData) -> pd.Series:
        close = data.bars["close"]
        e, x = self.params["entry"], self.params["exit"]
        upper = close.rolling(e).max().shift(1)      # canal de entrada (sin hoy)
        lower = close.rolling(e).min().shift(1)
        exit_up = close.rolling(x).max().shift(1)    # canal de salida (sin hoy)
        exit_dn = close.rolling(x).min().shift(1)

        # Lógica con estado (dentro/fuera) → bucle explícito; 5.400 días
        # es despreciable y se lee mejor que un ffill enrevesado.
        c = close.to_numpy()
        up, lo = upper.to_numpy(), lower.to_numpy()
        xu, xd = exit_up.to_numpy(), exit_dn.to_numpy()
        pos = np.full(len(c), np.nan)
        state = 0.0
        for i in range(len(c)):
            if np.isnan(up[i]):
                continue  # calentamiento del canal
            if state == 0.0:
                if c[i] > up[i]:
                    state = 1.0
                elif c[i] < lo[i]:
                    state = -1.0
            elif (state == 1.0 and c[i] < xd[i]) or (state == -1.0 and c[i] > xu[i]):
                state = 0.0  # tocó el extremo opuesto del canal de salida
            pos[i] = state
        return pd.Series(pos, index=close.index)
