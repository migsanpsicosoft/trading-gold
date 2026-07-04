"""Endpoints del gestor de riesgo (Fase 5)."""

from functools import lru_cache

import pandas as pd
from fastapi import APIRouter

from gold_bot.api.data import _data_version, _epoch
from gold_bot.data.db import connect
from gold_bot.meta_model.pipeline import load_meta_inputs
from gold_bot.risk.ensemble import ensemble_comparison
from gold_bot.risk.gating import current_gate_report

router = APIRouter(prefix="/api/risk")


@lru_cache(maxsize=1)
def _risk_for_version(version: tuple) -> dict:
    inputs = load_meta_inputs()
    comparison = ensemble_comparison(inputs)

    raw_nets = dict(inputs.daily_net)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        raw_nets[name] = net_daily
    gates_now = current_gate_report(raw_nets, inputs.regimes["regime"])

    def equity_points(net: pd.Series) -> list[dict]:
        import numpy as np

        equity = np.exp(net.reindex(inputs.regimes.index).fillna(0).cumsum())
        return [
            {"time": _epoch(ts.date().isoformat()), "value": round(float(v), 6)}
            for ts, v in equity.items()
        ]

    gates = comparison["gates"]
    recent = gates[gates.index >= "2012-01-01"]
    return {
        "metrics": comparison["metrics"],
        "equity_raw": equity_points(comparison["raw"]),
        "equity_gated": equity_points(comparison["gated"]),
        "gates_now": gates_now,
        "gate_on_pct": {c: round(float(recent[c].mean()), 3) for c in gates.columns},
    }


@router.get("")
def risk() -> dict:
    """Ensemble crudo vs con gating por régimen + estado actual de los gates."""
    conn = connect()
    try:
        version = _data_version(conn)
    finally:
        conn.close()
    return _risk_for_version(version)
