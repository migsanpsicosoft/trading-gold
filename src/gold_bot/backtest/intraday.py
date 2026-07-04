"""Motor de backtest intradía: simula por barra de 15m, reporta en diario.

Mismas dos protecciones que el motor diario:
  1. shift(1) POR BARRA: la señal de la barra t opera la barra t+1.
  2. Coste por cambio de posición con el spread REAL de esa barra
     (no el medio diario): pagar el spread de un NFP a las 14:30
     cuesta 10-30x el de una madrugada tranquila.

El PnL por barra se agrega a retornos diarios → las métricas, el split
IS/OOS y la correlación con las estrategias diarias son directamente
comparables.
"""

import numpy as np
import pandas as pd

from gold_bot.backtest.simple import (
    OOS_START,
    TRADING_DAYS,
    BacktestResult,
    compute_metrics,
)

FALLBACK_SPREAD_15M = 0.45  # $/oz si falta el spread de alguna barra
SLIPPAGE_BPS = 1.0


def run_intraday_backtest(bars15: pd.DataFrame, positions: pd.Series) -> BacktestResult:
    """Backtest de posiciones por barra de 15m.

    bars15: OHLC mid + spread (de load_intraday_ohlc).
    positions: posición objetivo en [-1, 1] por barra, calculada al
    cierre de cada barra.
    """
    mid = bars15["close"]
    ret = np.log(mid / mid.shift(1))

    pos = positions.reindex(mid.index).shift(1).fillna(0.0)
    gross = pos * ret

    spread_pct = (
        bars15["spread"].ffill().fillna(FALLBACK_SPREAD_15M) / mid
    )
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (spread_pct / 2 + SLIPPAGE_BPS / 10_000)

    net_15m = gross - cost

    # agregación a diario (solo días con barras; sin rellenar findes)
    day = net_15m.index.normalize()
    net_daily = net_15m.groupby(day).sum()
    positions_daily = pos.groupby(day).mean()  # sesgo direccional medio del día

    equity = np.exp(net_daily.cumsum())
    years = len(net_daily) / TRADING_DAYS
    metrics = {
        "full": compute_metrics(net_daily),
        "is": compute_metrics(net_daily[net_daily.index < OOS_START]),
        "oos": compute_metrics(net_daily[net_daily.index >= OOS_START]),
        "turnover_annual": float(turnover.sum() / years) if years > 0 else 0.0,
    }
    return BacktestResult(equity=equity, net_returns=net_daily,
                          positions=positions_daily, metrics=metrics)
