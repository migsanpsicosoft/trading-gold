"""Endpoints de la cartera multi-activo (expansión)."""

from functools import lru_cache

import numpy as np
import pandas as pd
from fastapi import APIRouter

from gold_bot.api.data import _data_version, _epoch
from gold_bot.api.risk import _portfolio_for_version
from gold_bot.data.db import connect
from gold_bot.risk.multi_asset import build_multi_portfolio

router = APIRouter(prefix="/api/multi")


@lru_cache(maxsize=1)
def _multi_for_version(version: tuple) -> dict:
    result = build_multi_portfolio()
    _inputs, _cmp, gold_portfolio = _portfolio_for_version(version)

    def equity_points(net: pd.Series) -> list[dict]:
        eq = np.exp(net.fillna(0).cumsum())
        return [
            {"time": _epoch(ts.date().isoformat()), "value": round(float(v), 6)}
            for ts, v in eq.items()
        ]

    books = result["books"]
    corr = result["correlation"]
    weights_now = result["asset_weights"].iloc[-1]

    return {
        "per_asset": [
            {
                "key": k,
                "name": b.config.name,
                "oos": {m: (None if v is None else round(v, 4))
                        for m, v in b.metrics["oos"].items()},
                "per_strategy": {s: (None if v is None else round(v, 2))
                                 for s, v in b.metrics["per_strategy_oos"].items()},
                "has_intraday": "vol_breakout" in b.nets,
                "weight_now": round(float(weights_now.get(k, 0.0)), 3),
            }
            for k, b in books.items()
        ],
        "correlation": {
            "names": list(corr.columns),
            "matrix": [[round(float(corr.iloc[i, j]), 3)
                        for j in range(len(corr.columns))]
                       for i in range(len(corr.columns))],
        },
        "combined_oos": {m: (None if v is None else round(v, 4))
                         for m, v in result["metrics"]["combined_oos"].items()},
        "gold_only_oos": {m: (None if v is None else round(v, 4))
                          for m, v in gold_portfolio["metrics"]["final_oos"].items()},
        "equity_combined": equity_points(result["final_returns"]),
        "equity_gold_only": equity_points(gold_portfolio["final_returns"]),
        "leverage_now": round(float(result["leverage"].iloc[-1]), 2),
        "brake_now": round(float(result["brake"].iloc[-1]), 2),
    }


@router.get("")
def multi() -> dict:
    """Cartera multi-activo: libros, correlaciones y comparación vs solo-oro."""
    conn = connect()
    try:
        version = _data_version(conn)
    finally:
        conn.close()
    return _multi_for_version(version)
