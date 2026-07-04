"""Motor de backtest vectorizado para cribar estrategias (Fase 2).

Es deliberadamente simple: posición diaria × retorno diario − costes.
El walk-forward con re-entrenamiento llegará en Fase 6; esto responde
a "¿esta estrategia merece seguir viva?" con costes realistas.

LAS DOS LÍNEAS QUE EVITAN AUTOENGAÑOS:

  1. positions.shift(1): la señal calculada al cierre de t opera el
     retorno de t+1. Sin esto, el backtest "opera el pasado" y los
     Sharpe salen inflados. Error nº 1 de los backtests amateur.

  2. Coste por cruzar el spread en cada cambio de posición, con el
     spread REAL medido barra a barra (Dukascopy). Un backtest sin
     costes no cuenta como backtest (regla del proyecto).

Split IS/OOS: in-sample hasta OOS_START, out-of-sample después. El
filtro de criba (Sharpe > 0.5) se evalúa SOLO en OOS.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252
OOS_START = "2019-01-01"     # IS: 2005-2018 · OOS: 2019-hoy
FALLBACK_SPREAD = 0.45       # $/oz donde no hay intradía (pre-2015); conservador
SLIPPAGE_BPS = 1.0           # deslizamiento adicional por transacción


@dataclass
class BacktestResult:
    equity: pd.Series          # curva de capital (base 1.0)
    net_returns: pd.Series     # retornos log netos diarios
    positions: pd.Series       # posición efectiva (ya con shift)
    metrics: dict              # {"full": {...}, "is": {...}, "oos": {...}}


def compute_metrics(net_returns: pd.Series) -> dict:
    """Métricas estándar sobre retornos log diarios netos."""
    r = net_returns.dropna()
    if len(r) < 20 or r.std() == 0:
        return {"sharpe": None, "cagr": None, "max_drawdown": None,
                "vol": None, "days": len(r)}
    equity = np.exp(r.cumsum())
    peak = equity.cummax()
    max_dd = float((equity / peak - 1).min())
    years = len(r) / TRADING_DAYS
    return {
        "sharpe": float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)),
        "cagr": float(equity.iloc[-1] ** (1 / years) - 1),
        "max_drawdown": max_dd,
        "vol": float(r.std() * np.sqrt(TRADING_DAYS)),
        "days": len(r),
    }


def run_backtest(bars: pd.DataFrame, positions: pd.Series,
                 spread_usd: pd.Series | None = None) -> BacktestResult:
    """Backtest vectorizado de una serie de posiciones objetivo.

    bars: OHLCV diario (usa close).
    positions: posición objetivo en [-1, 1] calculada al cierre de cada día.
    spread_usd: spread bid/ask medio diario en $ (de features.spread_mean);
                donde falte se usa FALLBACK_SPREAD.
    """
    close = bars["close"]
    ret = np.log(close / close.shift(1))

    # (1) la señal del cierre de t gana el retorno de t+1
    pos = positions.reindex(close.index).shift(1).fillna(0.0)

    gross = pos * ret

    # (2) coste de transacción: |Δposición| × (spread/2 + slippage)
    # comprar cruza al ask (mid + spread/2), vender al bid → cada
    # transacción paga medio spread por unidad de posición cambiada
    if spread_usd is None:
        spread_usd = pd.Series(FALLBACK_SPREAD, index=close.index)
    spread_pct = (spread_usd.reindex(close.index).ffill().fillna(FALLBACK_SPREAD)) / close
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (spread_pct / 2 + SLIPPAGE_BPS / 10_000)

    net = gross - cost
    equity = np.exp(net.cumsum())

    metrics = {
        "full": compute_metrics(net),
        "is": compute_metrics(net[net.index < OOS_START]),
        "oos": compute_metrics(net[net.index >= OOS_START]),
        "turnover_annual": float(turnover.sum() / (len(net) / TRADING_DAYS)),
    }
    return BacktestResult(equity=equity, net_returns=net, positions=pos,
                          metrics=metrics)
