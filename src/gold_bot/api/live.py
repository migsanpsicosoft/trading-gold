"""Endpoints del paper trading en vivo (Fase 7)."""

import numpy as np
from fastapi import APIRouter

from gold_bot.api.data import _data_version, _epoch
from gold_bot.api.risk import _portfolio_for_version
from gold_bot.data.db import connect

router = APIRouter(prefix="/api/live")


@router.get("")
def live() -> dict:
    """Registro del runner diario + comparación contra el backtest teórico."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT ts, exposure, price, balance, currency, held_units, "
            "target_units, order_units, dry_run FROM live_log ORDER BY ts"
        ).fetchall()
        version = _data_version(conn)
    finally:
        conn.close()

    if not rows:
        return {"runs": [], "live_equity": [], "backtest_equity": []}

    runs = [
        {"ts": r[0], "exposure": r[1], "price": r[2], "balance": r[3],
         "currency": r[4], "held_units": r[5], "target_units": r[6],
         "order_units": r[7], "dry_run": bool(r[8])}
        for r in rows
    ]

    # equity live normalizada a 1.0 en el primer día de paper trading
    first_balance = rows[0][3]
    live_equity = [
        {"time": _epoch(r[0][:10]), "value": round(r[3] / first_balance, 6)}
        for r in rows
    ]

    # backtest teórico normalizado en la misma fecha
    _inputs, _cmp, portfolio = _portfolio_for_version(version)
    final = portfolio["final_returns"]
    start = rows[0][0][:10]
    window = final[final.index >= start]
    bt_equity = np.exp(window.cumsum())
    backtest_equity = [
        {"time": _epoch(ts.date().isoformat()), "value": round(float(v), 6)}
        for ts, v in bt_equity.items()
    ]

    return {"runs": runs[::-1][:60], "live_equity": live_equity,
            "backtest_equity": backtest_equity}
