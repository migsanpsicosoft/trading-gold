"""Endpoints de estrategias: catálogo y backtest individual (Fase 2)."""

from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException

from gold_bot.api.data import _data_version, _epoch, _features_for_version
from gold_bot.backtest.simple import OOS_START, BacktestResult, run_backtest
from gold_bot.data.db import connect
from gold_bot.data.download import load_bars
from gold_bot.strategies import STRATEGIES
from gold_bot.strategies.base import StrategyData

router = APIRouter(prefix="/api/strategies")

OOS_SHARPE_THRESHOLD = 0.5  # filtro de criba de la Fase 2


@lru_cache(maxsize=16)
def _backtest_cached(version: tuple, name: str) -> BacktestResult:
    conn = connect()
    try:
        bars = load_bars(conn, "XAU")
    finally:
        conn.close()
    features = _features_for_version(version)
    positions = STRATEGIES[name].generate_positions(
        StrategyData(bars=bars, features=features)
    )
    spread = features.get("spread_mean")
    return run_backtest(bars, positions, spread_usd=spread)


def _run(name: str) -> BacktestResult:
    conn = connect()
    try:
        version = _data_version(conn)
    finally:
        conn.close()
    return _backtest_cached(version, name)


@router.get("")
def list_strategies() -> list[dict]:
    """Catálogo con el veredicto de criba de cada estrategia."""
    out = []
    for name, strat in STRATEGIES.items():
        result = _run(name)
        oos_sharpe = result.metrics["oos"]["sharpe"]
        out.append({
            "name": name,
            "description": strat.description,
            "params": strat.params,
            "oos_sharpe": oos_sharpe,
            "passes_filter": oos_sharpe is not None and oos_sharpe > OOS_SHARPE_THRESHOLD,
        })
    return out


@router.get("/{name}")
def strategy_backtest(name: str) -> dict:
    """Backtest completo: métricas IS/OOS, equity curve y posiciones."""
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Estrategia desconocida: {name}")
    result = _run(name)

    def series_points(s: pd.Series) -> list[dict]:
        return [
            {"time": _epoch(ts.date().isoformat()), "value": round(float(v), 6)}
            for ts, v in s.dropna().items()
        ]

    return {
        "name": name,
        "description": STRATEGIES[name].description,
        "params": STRATEGIES[name].params,
        "metrics": result.metrics,
        "oos_start": OOS_START,
        "equity": series_points(result.equity),
        "positions": series_points(result.positions),
    }
