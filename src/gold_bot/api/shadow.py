"""Tracking de los libros sombra: PnL virtual desde las señales registradas.

La evidencia es inviolable por orden temporal: la exposición se registra
al cierre de t (antes de conocer t+1); el PnL virtual del día t+1 es
Σ exposición(t) × retorno(t+1) − |Δexposición| × spread/2. Los precios
y spreads salen de nuestra propia base (auto-actualizada).
"""

import numpy as np
import pandas as pd
from fastapi import APIRouter

from gold_bot.api.data import _epoch
from gold_bot.data.db import connect

router = APIRouter(prefix="/api/shadow")


def _asset_returns(conn, assets: list[str]) -> pd.DataFrame:
    frames = {}
    for asset in assets:
        rows = conn.execute(
            "SELECT date, close FROM bars WHERE symbol = ? ORDER BY date", (asset,)
        ).fetchall()
        s = pd.Series({pd.Timestamp(d): c for d, c in rows})
        frames[asset] = np.log(s / s.shift(1))
    return pd.DataFrame(frames)


@router.get("")
def shadow() -> dict:
    """PnL virtual acumulado de cada libro sombra + últimas exposiciones."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts, book, asset, exposure FROM shadow_signals ORDER BY ts"
        ).fetchall()
        if not rows:
            return {"books": {}, "days_tracked": 0}
        signals = pd.DataFrame(rows, columns=["ts", "book", "asset", "exposure"])
        signals["date"] = pd.to_datetime(signals["ts"].str[:10])
        assets = sorted(signals["asset"].unique())
        returns = _asset_returns(conn, assets)
    finally:
        conn.close()

    out: dict = {"books": {}, "cells": [], "days_tracked": 0}
    for book_name, group in signals.groupby("book"):
        # células individuales (validación por estrategia): resumen compacto
        if book_name.startswith("cell_"):
            strategy = book_name[5:]
            exp = (group.sort_values("ts").groupby(["date", "asset"])["exposure"]
                   .last().unstack().sort_index())
            if len(exp) >= 2:
                aligned = returns.reindex(index=exp.index, columns=exp.columns)
                pnl = (exp.shift(1) * aligned).sum(axis=1).fillna(0.0)
                for asset in exp.columns:
                    cell_pnl = (exp[asset].shift(1)
                                * aligned[asset]).fillna(0.0)
                    out["cells"].append({
                        "strategy": strategy,
                        "asset": asset,
                        "days": int(len(exp)),
                        "virtual_return": round(float(np.exp(cell_pnl.sum()) - 1), 4),
                    })
            else:
                for asset in group["asset"].unique():
                    out["cells"].append({"strategy": strategy, "asset": asset,
                                         "days": int(len(exp)),
                                         "virtual_return": None})
            continue
        # una exposición por (día, activo): la última registrada ese día
        exp = (group.sort_values("ts").groupby(["date", "asset"])["exposure"]
               .last().unstack().sort_index())
        if len(exp) < 2:
            latest = exp.iloc[-1].fillna(0.0) if len(exp) else pd.Series(dtype=float)
            out["books"][book_name] = {
                "days": int(len(exp)),
                "virtual_return": None,
                "equity": [],
                "latest_exposures": {k: round(float(v), 4)
                                     for k, v in latest.items()},
            }
            continue

        # exposición de t aplica al retorno de t+1 (orden temporal estricto)
        aligned = returns.reindex(index=exp.index, columns=exp.columns)
        pnl = (exp.shift(1) * aligned).sum(axis=1).fillna(0.0)
        equity = np.exp(pnl.cumsum())
        out["books"][book_name] = {
            "days": int(len(exp)),
            "virtual_return": round(float(equity.iloc[-1] - 1), 4),
            "equity": [
                {"time": _epoch(d.date().isoformat()), "value": round(float(v), 6)}
                for d, v in equity.items()
            ],
            "latest_exposures": {k: round(float(v), 4)
                                 for k, v in exp.iloc[-1].fillna(0.0).items()},
        }
        out["days_tracked"] = max(out["days_tracked"], int(len(exp)))
    return out
