"""Series macro de FRED (sin API key) para las estrategias de carry.

FRED expone cualquier serie como CSV en fredgraph.csv?id=SERIE — sin
registro. Series elegidas (pre-registro v3):

  US3M    DTB3              T-Bill 3 meses USA (diario)
  ECB     ECBDFR            Tipo de depósito BCE (diario)
  JPRATE  IRSTCI01JPM156N   Call rate Japón (mensual — los tipos BOJ
                            se mueven poco; suficiente para carry)
  T10Y2Y  T10Y2Y            Pendiente 10a-2a USA (diario)

Los valores faltantes de FRED vienen como '.' → NaN → ffill al usar.
"""

import sqlite3

import pandas as pd
import requests

from gold_bot.utils.log import get_logger

log = get_logger(__name__)

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"

FRED_SERIES: dict[str, str] = {
    "US3M": "DTB3",
    "ECB": "ECBDFR",
    "JPRATE": "IRSTCI01JPM156N",
    "T10Y2Y": "T10Y2Y",
}


def fetch_fred(series_id: str) -> pd.Series:
    """Descarga una serie completa de FRED (ficheros pequeños)."""
    r = requests.get(FRED_URL.format(series=series_id), timeout=60)
    r.raise_for_status()
    from io import StringIO

    df = pd.read_csv(StringIO(r.text))
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"]


def update_macro(conn: sqlite3.Connection) -> dict:
    """Refetch completo (las series son pequeñas) + upsert idempotente."""
    total = 0
    for key, series_id in FRED_SERIES.items():
        try:
            s = fetch_fred(series_id)
        except Exception as exc:
            log.error("fred_fallo", serie=key, error=str(exc))
            continue
        rows = [(key, d, float(v)) for d, v in s.items()]
        conn.executemany(
            "INSERT INTO aux_series (series, date, value) VALUES (?, ?, ?) "
            "ON CONFLICT (series, date) DO UPDATE SET value = excluded.value",
            rows,
        )
        total += len(rows)
    conn.commit()
    log.info("macro_actualizado", filas=total)
    return {"rows_upserted": total}


def load_macro_daily(conn: sqlite3.Connection, key: str,
                     index: pd.DatetimeIndex) -> pd.Series:
    """Serie alineada a `index` con ffill (el último dato conocido)."""
    rows = conn.execute(
        "SELECT date, value FROM aux_series WHERE series = ? ORDER BY date",
        (key,),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float, index=index)
    s = pd.Series({pd.Timestamp(d): v for d, v in rows})
    return s.reindex(index.union(s.index)).ffill().reindex(index)
