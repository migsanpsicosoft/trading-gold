"""Gating adaptativo por régimen (Fase 5, pieza 1).

La Fase 3 demostró que cada estrategia tiene su hábitat (Sharpe ±1.0
según régimen) y la Fase 4 que ese edge no se explota filtrando señal
a señal (AUC 0.51) — se explota AGREGANDO. Este módulo lo hace de la
forma más simple posible:

  gate(estrategia, día) = 1 si su Sharpe móvil en los últimos
  LOOKBACK días DE ESTE MISMO RÉGIMEN es > 0; si no, 0.

Nada cableado a mano (no usamos la tabla de la F3 — sería in-sample):
el gate aprende sola y walk-forward qué estrategia funciona en qué
régimen, y se adapta si eso cambia.

Anti-leakage: el Sharpe condicional lleva shift(1) sobre los días del
régimen (solo días anteriores) y el régimen del día viene del HMM
filtrado (solo pasado por construcción). Con historial insuficiente
(<MIN_REGIME_DAYS días en ese régimen) el gate queda en 1: las
estrategias pasaron la criba y por defecto están vivas.
"""

import numpy as np
import pandas as pd

LOOKBACK_REGIME_DAYS = 250  # días EN el régimen (≈1 año de ese hábitat)
MIN_REGIME_DAYS = 60        # mínimo para opinar; antes, gate neutro = 1
TRADING_DAYS = 252


def conditional_gate(net: pd.Series, regime: pd.Series) -> pd.Series:
    """Gate diario {0, 1} de una estrategia según el régimen del día.

    net: retornos netos diarios de la estrategia.
    regime: régimen del día (int), índice de referencia del resultado.
    """
    net = net.reindex(regime.index)
    gate = pd.Series(1.0, index=regime.index)

    for k in sorted(regime.dropna().unique()):
        mask = regime == k
        sub = net[mask]
        roll = sub.rolling(LOOKBACK_REGIME_DAYS, min_periods=MIN_REGIME_DAYS)
        sharpe = (roll.mean() / roll.std() * np.sqrt(TRADING_DAYS)).shift(1)
        gate[mask] = np.where(sharpe.isna(), 1.0, (sharpe > 0).astype(float))

    return gate


def gate_matrix(nets: dict[str, pd.Series], regime: pd.Series) -> pd.DataFrame:
    """Gates diarios de todas las estrategias (columnas)."""
    return pd.DataFrame(
        {name: conditional_gate(net, regime) for name, net in nets.items()}
    )


def current_gate_report(nets: dict[str, pd.Series], regime: pd.Series) -> list[dict]:
    """Estado actual de cada gate, con el Sharpe condicional que lo justifica."""
    today_regime = int(regime.iloc[-1])
    out = []
    for name, net in nets.items():
        net = net.reindex(regime.index)
        sub = net[regime == today_regime]
        window = sub.iloc[:-1].tail(LOOKBACK_REGIME_DAYS)  # sin el día de hoy
        if len(window) >= MIN_REGIME_DAYS and window.std() > 0:
            sharpe = float(window.mean() / window.std() * np.sqrt(TRADING_DAYS))
            gate_on = sharpe > 0
        else:
            sharpe, gate_on = None, True
        out.append({"strategy": name, "regime": today_regime,
                    "cond_sharpe": sharpe, "gate_on": bool(gate_on)})
    return out
