"""Descarga incremental de datos diarios desde Yahoo Finance.

Diseño:
  - fetch_bars() es la ÚNICA función que toca la red (yfinance).
    Todo lo demás (upsert, fechas incrementales, hash, staleness)
    es lógica pura sobre SQLite → testeable sin conexión.
  - Incremental con solape: al actualizar re-descargamos los últimos
    OVERLAP_DAYS días aunque ya los tengamos, porque Yahoo corrige a
    veces datos recientes. El upsert (PK symbol+date) los machaca
    sin duplicar.
"""

import hashlib
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import yfinance as yf

from gold_bot.utils.log import get_logger

log = get_logger(__name__)

# Símbolo interno → (ticker de Yahoo, descripción)
SYMBOLS: dict[str, tuple[str, str]] = {
    "XAU": ("GC=F", "Oro — futuros COMEX front month"),
    "XAG": ("SI=F", "Plata — futuros COMEX front month"),
    "DXY": ("DX-Y.NYB", "Índice dólar (ICE)"),
    "US10Y": ("^TNX", "Yield Treasury 10 años (en % x10)"),
    "TIP": ("TIP", "ETF de TIPS — proxy de tipos reales"),
}

HISTORY_START = "2005-01-01"  # ~20 años: cubre varios regímenes de mercado
OVERLAP_DAYS = 7              # margen re-descargado por si Yahoo corrige datos
STALE_AFTER_HOURS = 24        # con datos diarios, más frecuente no aporta

BAR_COLUMNS = ["open", "high", "low", "close", "volume"]


# ------------------------------------------------------------------ red
def fetch_bars(yahoo_ticker: str, start: str) -> pd.DataFrame:
    """Descarga OHLCV diario desde Yahoo. Única función con I/O de red.

    Devuelve DataFrame con índice de fechas ISO (str) y columnas
    open/high/low/close/volume. auto_adjust=True ajusta por splits
    y dividendos (relevante para TIP; inocuo para futuros e índices).
    """
    raw = yf.Ticker(yahoo_ticker).history(start=start, auto_adjust=True, raise_errors=True)
    if raw.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)
    df = raw.rename(columns=str.lower)[BAR_COLUMNS].copy()
    df.index = [d.date().isoformat() for d in df.index]
    # Sin volumen real (índices, yields): Yahoo devuelve 0 → NULL en la DB
    if (df["volume"] == 0).all():
        df["volume"] = None
    return df


# ----------------------------------------------------------- lógica pura
def upsert_bars(conn: sqlite3.Connection, symbol: str, df: pd.DataFrame) -> int:
    """Inserta o actualiza barras. Idempotente gracias a la PK (symbol, date)."""
    if df.empty:
        return 0
    rows = [
        (symbol, idx, r.open, r.high, r.low, r.close, r.volume)
        for idx, r in df.iterrows()
        if pd.notna(r.close)
    ]
    conn.executemany(
        """
        INSERT INTO bars (symbol, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, date) DO UPDATE SET
            open = excluded.open, high = excluded.high, low = excluded.low,
            close = excluded.close, volume = excluded.volume
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def incremental_start(conn: sqlite3.Connection, symbol: str) -> str:
    """Fecha desde la que descargar: última barra menos el solape."""
    last = conn.execute("SELECT MAX(date) FROM bars WHERE symbol = ?", (symbol,)).fetchone()[0]
    if last is None:
        return HISTORY_START
    return (date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS)).isoformat()


def dataset_hash(conn: sqlite3.Connection, symbol: str) -> str:
    """sha256 del contenido de un símbolo. Identifica el dataset exacto."""
    h = hashlib.sha256()
    for row in conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ? ORDER BY date",
        (symbol,),
    ):
        h.update(repr(row).encode())
    return h.hexdigest()


def _touch_meta(conn: sqlite3.Connection, symbol: str) -> str:
    content_hash = dataset_hash(conn, symbol)
    conn.execute(
        """
        INSERT INTO dataset_meta (symbol, last_updated, content_hash) VALUES (?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            last_updated = excluded.last_updated, content_hash = excluded.content_hash
        """,
        (symbol, datetime.now(UTC).isoformat(), content_hash),
    )
    conn.commit()
    return content_hash


def is_stale(conn: sqlite3.Connection) -> bool:
    """True si algún símbolo no se ha actualizado en STALE_AFTER_HOURS."""
    threshold = datetime.now(UTC) - timedelta(hours=STALE_AFTER_HOURS)
    for symbol in SYMBOLS:
        row = conn.execute(
            "SELECT last_updated FROM dataset_meta WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row is None or datetime.fromisoformat(row[0]) < threshold:
            return True
    return False


# ------------------------------------------------------------ orquestación
def update_symbol(conn: sqlite3.Connection, symbol: str) -> dict:
    """Actualización incremental de un símbolo. Devuelve resumen."""
    yahoo_ticker, _ = SYMBOLS[symbol]
    start = incremental_start(conn, symbol)
    df = fetch_bars(yahoo_ticker, start)
    n_rows = upsert_bars(conn, symbol, df)
    content_hash = _touch_meta(conn, symbol)
    log.info("simbolo_actualizado", symbol=symbol, desde=start, filas=n_rows)
    return {"symbol": symbol, "fetched_from": start, "rows_upserted": n_rows,
            "content_hash": content_hash}


def update_all(conn: sqlite3.Connection) -> list[dict]:
    """Actualiza todos los símbolos; un fallo en uno no frena a los demás."""
    results = []
    for symbol in SYMBOLS:
        try:
            results.append(update_symbol(conn, symbol))
        except Exception as exc:  # red caída, ticker delistado, etc.
            log.error("fallo_actualizando", symbol=symbol, error=str(exc))
            results.append({"symbol": symbol, "error": str(exc)})
    return results


def data_summary(conn: sqlite3.Connection) -> list[dict]:
    """Estado por símbolo: filas, rango de fechas, última actualización, hash."""
    out = []
    for symbol, (yahoo_ticker, description) in SYMBOLS.items():
        n, first, last = conn.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM bars WHERE symbol = ?", (symbol,)
        ).fetchone()
        meta = conn.execute(
            "SELECT last_updated, content_hash FROM dataset_meta WHERE symbol = ?", (symbol,)
        ).fetchone()
        out.append({
            "symbol": symbol,
            "yahoo_ticker": yahoo_ticker,
            "description": description,
            "rows": n,
            "first_date": first,
            "last_date": last,
            "last_updated": meta[0] if meta else None,
            "content_hash": meta[1] if meta else None,
        })
    return out


def load_bars(conn: sqlite3.Connection, symbol: str, start: str | None = None) -> pd.DataFrame:
    """Barras de un símbolo como DataFrame indexado por fecha."""
    query = "SELECT date, open, high, low, close, volume FROM bars WHERE symbol = ?"
    params: list = [symbol]
    if start:
        query += " AND date >= ?"
        params.append(start)
    df = pd.read_sql(query + " ORDER BY date", conn, params=params, index_col="date")
    df.index = pd.to_datetime(df.index)
    return df
