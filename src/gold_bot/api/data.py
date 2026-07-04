"""Endpoints de datos del dashboard.

Cada petición abre su propia conexión SQLite (no se comparten entre
hilos). Para barras diarias e intradía el coste es despreciable.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter, HTTPException

from gold_bot.data.db import connect
from gold_bot.data.download import SYMBOLS, data_summary, load_bars, update_all
from gold_bot.data.features import FEATURE_DESCRIPTIONS, compute_features
from gold_bot.data.intraday import (
    INTRADAY_SYMBOLS,
    intraday_summary,
    load_intraday_mid,
    resample_bars,
    update_intraday,
)

router = APIRouter(prefix="/api/data")

INTRADAY_DEFAULT_DAYS = 60  # sin filtro, el intradía devolvería ~400k barras


def _epoch(iso: str) -> int:
    """'yyyy-mm-dd[Thh:mm:ss]' (UTC) → segundos epoch (lightweight-charts)."""
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp())


@router.get("/summary")
def summary() -> list[dict]:
    """Estado por dataset (diarios + intradía)."""
    conn = connect()
    try:
        return data_summary(conn) + intraday_summary(conn)
    finally:
        conn.close()


@router.post("/update")
def update() -> list[dict]:
    """Actualización incremental de todo (botón del dashboard).

    Ojo: si el intradía está vacío, esto lanza el backfill completo
    (años) y puede tardar bastantes minutos.
    """
    conn = connect()
    try:
        results = update_all(conn)
        for symbol in INTRADAY_SYMBOLS:
            try:
                results.append(update_intraday(conn, symbol))
            except Exception as exc:
                results.append({"symbol": symbol, "error": str(exc)})
        return results
    finally:
        conn.close()


def _daily_bars(conn, symbol: str, start: str | None) -> list[dict]:
    query = (
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE symbol = ?" + (" AND date >= ?" if start else "") + " ORDER BY date"
    )
    params = (symbol, start) if start else (symbol,)
    return [
        {"time": _epoch(d), "open": o, "high": h, "low": lo, "close": c, "volume": v}
        for d, o, h, lo, c, v in conn.execute(query, params)
    ]


def _intraday_bars(conn, symbol: str, start: str | None, resample_to: str | None) -> list[dict]:
    if start is None:
        start = (datetime.now(UTC) - timedelta(days=INTRADAY_DEFAULT_DAYS)).date().isoformat()
    df = pd.read_sql(
        """
        SELECT ts, bid_open AS open, bid_high AS high, bid_low AS low,
               bid_close AS close, volume, ask_close - bid_close AS spread
        FROM intraday_bars
        WHERE symbol = ? AND ts >= ? AND bid_close IS NOT NULL
        ORDER BY ts
        """,
        conn,
        params=(symbol, start),
        index_col="ts",
    )
    df.index = pd.to_datetime(df.index)
    if resample_to:
        spread = df.pop("spread").resample(resample_to).mean()
        df = resample_bars(df, resample_to)
        df["spread"] = spread
    return [
        {
            "time": _epoch(ts.isoformat()),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "spread": None if pd.isna(r.spread) else round(r.spread, 3),
        }
        for ts, r in df.iterrows()
    ]


# -------------------------------------------------------------- features
def _data_version(conn) -> tuple:
    """Estado exacto de los datos: los content hashes de dataset_meta.

    Sirve de clave de caché: si ningún hash cambió, las features
    calculadas siguen siendo válidas y no se recalculan.
    """
    return tuple(conn.execute(
        "SELECT symbol, content_hash FROM dataset_meta ORDER BY symbol"
    ).fetchall())


@lru_cache(maxsize=2)
def _features_for_version(version: tuple) -> pd.DataFrame:
    conn = connect()
    try:
        daily = {sym: load_bars(conn, sym) for sym in SYMBOLS}
        intraday = load_intraday_mid(conn, "XAU")
        # Se calcula SIEMPRE sobre el histórico completo: las ventanas
        # móviles necesitan calentamiento; se filtra por fecha después.
        return compute_features(daily, intraday)
    finally:
        conn.close()


def _features_df() -> pd.DataFrame:
    conn = connect()
    try:
        return _features_for_version(_data_version(conn))
    finally:
        conn.close()


@router.get("/features")
def features_meta() -> dict:
    """Catálogo de features + snapshot de los últimos valores."""
    f = _features_df()
    latest = f.iloc[-1]
    return {
        "names": list(f.columns),
        "descriptions": FEATURE_DESCRIPTIONS,
        "latest_date": f.index[-1].date().isoformat(),
        "latest": {
            k: (None if pd.isna(v) else round(float(v), 6)) for k, v in latest.items()
        },
    }


@router.get("/features/{name}")
def feature_series(name: str, start: str | None = None) -> list[dict]:
    """Serie temporal de una feature para el gráfico."""
    f = _features_df()
    if name not in f.columns:
        raise HTTPException(status_code=404, detail=f"Feature desconocida: {name}")
    s = f[name].dropna()
    if start:
        s = s[s.index >= start]
    return [
        {"time": _epoch(ts.date().isoformat()), "value": round(float(v), 6)}
        for ts, v in s.items()
    ]


@router.get("/bars/{symbol}")
def bars(symbol: str, timeframe: str = "D", start: str | None = None) -> list[dict]:
    """OHLCV para el gráfico. timeframe: D (diario), 1h, 15m.

    time = segundos epoch UTC. El intradía incluye el spread bid/ask
    real de cada barra (media, si está re-agregado a 1h).
    """
    conn = connect()
    try:
        if timeframe == "D":
            if symbol not in SYMBOLS:
                raise HTTPException(status_code=404, detail=f"Símbolo desconocido: {symbol}")
            return _daily_bars(conn, symbol, start)
        if timeframe in ("15m", "1h"):
            if symbol not in INTRADAY_SYMBOLS:
                raise HTTPException(
                    status_code=404, detail=f"Sin datos intradía para: {symbol}"
                )
            return _intraday_bars(conn, symbol, start, "1h" if timeframe == "1h" else None)
        raise HTTPException(status_code=400, detail=f"Timeframe no soportado: {timeframe}")
    finally:
        conn.close()
