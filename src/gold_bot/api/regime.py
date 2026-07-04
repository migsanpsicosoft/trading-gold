"""Endpoints del detector de régimen (Fase 3)."""

from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter

from gold_bot.api.data import _data_version, _epoch, _features_for_version
from gold_bot.api.strategies import ALL_STRATEGIES, _run
from gold_bot.data.db import connect
from gold_bot.regime.hmm import N_STATES, regime_stats, walkforward_regimes

router = APIRouter(prefix="/api/regime")

TRADING_DAYS = 252


@lru_cache(maxsize=2)
def _regimes_for_version(version: tuple) -> pd.DataFrame:
    features = _features_for_version(version)
    return walkforward_regimes(features)


def _current() -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = connect()
    try:
        version = _data_version(conn)
    finally:
        conn.close()
    return _regimes_for_version(version), _features_for_version(version)


def _sharpe(returns: pd.Series) -> float | None:
    r = returns.dropna()
    if len(r) < 60 or r.std() == 0:
        return None
    return float(r.mean() / r.std() * np.sqrt(TRADING_DAYS))


@router.get("")
def regime() -> dict:
    """Serie de regímenes walk-forward + caracterización + Sharpe de cada
    estrategia condicionado al régimen del día."""
    regimes, features = _current()

    prob_cols = [f"prob_{i}" for i in range(N_STATES)]
    series = [
        {
            "time": _epoch(ts.date().isoformat()),
            "regime": int(row["regime"]),
            "probs": [round(float(row[c]), 4) for c in prob_cols],
        }
        for ts, row in regimes.iterrows()
    ]

    # Sharpe por régimen: la evidencia de si el régimen informa
    by_regime = {}
    for name in ALL_STRATEGIES:
        net = _run(name).net_returns
        regime_of_day = regimes["regime"].reindex(net.index)
        by_regime[name] = [
            _sharpe(net[regime_of_day == k]) for k in range(N_STATES)
        ]

    return {
        "states": regime_stats(features, regimes),
        "series": series,
        "sharpe_by_regime": by_regime,
    }
