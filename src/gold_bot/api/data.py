"""Endpoints de datos del dashboard.

Cada petición abre su propia conexión SQLite (no se comparten entre
hilos). Para barras diarias el coste es despreciable.
"""

from fastapi import APIRouter, HTTPException

from gold_bot.data.db import connect
from gold_bot.data.download import SYMBOLS, data_summary, update_all

router = APIRouter(prefix="/api/data")


@router.get("/summary")
def summary() -> list[dict]:
    """Estado por símbolo: filas, rango de fechas, última actualización, hash."""
    conn = connect()
    try:
        return data_summary(conn)
    finally:
        conn.close()


@router.post("/update")
def update() -> list[dict]:
    """Actualización incremental de todos los símbolos (botón del dashboard)."""
    conn = connect()
    try:
        return update_all(conn)
    finally:
        conn.close()


@router.get("/bars/{symbol}")
def bars(symbol: str, start: str | None = None) -> list[dict]:
    """OHLCV diario en el formato que espera lightweight-charts:
    [{time: 'yyyy-mm-dd', open, high, low, close, volume}, ...]
    """
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Símbolo desconocido: {symbol}")
    conn = connect()
    try:
        query = (
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE symbol = ?" + (" AND date >= ?" if start else "") + " ORDER BY date"
        )
        params = (symbol, start) if start else (symbol,)
        return [
            {"time": d, "open": o, "high": h, "low": lo, "close": c, "volume": v}
            for d, o, h, lo, c, v in conn.execute(query, params)
        ]
    finally:
        conn.close()
