"""Descarga incremental de barras intradía (15m) desde Dukascopy.

Dukascopy publica su histórico gratis y sin cuenta, con velas BID y ASK
por separado → tenemos el spread real de cada barra, imprescindible
para modelar costes realistas (el spread del oro se dispara en NFP,
CPI y FOMC).

La descarga la hace `dukascopy-node` (npx) en un subprocess: el formato
binario .bi5 de Dukascopy tiene trampas (meses 0-indexados, escala de
precio por instrumento, LZMA crudo) que esa herramienta ya resuelve.
Igual que en download.py: la red vive en UNA función (fetch_intraday);
el resto es lógica pura testeable.

Timestamps siempre en UTC. Las sesiones (Asia/Londres/NY) se derivarán
en la capa de features, no aquí.
"""

import shutil
import sqlite3
import subprocess
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from gold_bot.utils.log import get_logger

log = get_logger(__name__)

# Símbolo interno → instrumento de Dukascopy
INTRADAY_SYMBOLS: dict[str, str] = {
    "XAU": "xauusd",
    "XAG": "xagusd",
    "EUR": "eurusd",
    "WTI": "lightcmdusd",
    "SPX": "usa500idxusd",
    "JPY": "usdjpy",
    "HG": "coppercmdusd",
    "NG": "gascmdusd",
    "USB": "ustbondtrusd",
}
INTRADAY_TIMEFRAME = "m15"
# El oro conserva su histórico desde 2015; los activos añadidos en la
# expansión multi-activo empiezan en 2019 (7 años intradía bastan y
# el backfill cuesta la mitad)
INTRADAY_HISTORY_START = "2015-01-01"
INTRADAY_START: dict[str, str] = {"XAU": "2015-01-01"}
DEFAULT_INTRADAY_START = "2019-01-01"
INTRADAY_OVERLAP_DAYS = 3              # margen re-descargado en cada actualización
CHUNK_RETRIES = 4                      # Dukascopy a veces rechaza bajo carga (transitorio)

OHLC = ["open", "high", "low", "close"]


def meta_key(symbol: str) -> str:
    """Clave en dataset_meta (p. ej. 'XAU_m15'), separada del diario."""
    return f"{symbol}_{INTRADAY_TIMEFRAME}"


# ------------------------------------------------------------------ red
def fetch_intraday(instrument: str, side: str, date_from: str, date_to: str) -> pd.DataFrame:
    """Descarga velas bid o ask vía dukascopy-node. Única función con red.

    Devuelve DataFrame con índice ts (ISO UTC) y columnas open/high/low/
    close/volume. Puede tardar minutos en rangos largos (un fichero por
    día en origen).
    """
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx no encontrado: dukascopy-node necesita Node.js en el PATH")

    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            npx, "-y", "dukascopy-node",
            "-i", instrument,
            "-from", date_from,
            "-to", date_to,
            "-t", INTRADAY_TIMEFRAME,
            "-p", side,
            "-f", "csv",
            "-v",
            "-s",
            # -r reintenta descargas FALLIDAS (red); con fail-after-retries
            # (default) el proceso muere en vez de dejar huecos silenciosos.
            # OJO: no usar -re (retry-on-empty): los festivos recientes
            # tienen ficheros legítimamente vacíos (0 bytes) y -re aborta
            # la descarga entera al agotarse los reintentos. Los huecos
            # reales se vigilan a posteriori con el chequeo de integridad.
            "-r", "5",
            "-rp", "1000",
            "-dir", tmp,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600 * 2)
        if result.returncode != 0:
            raise RuntimeError(f"dukascopy-node falló: {result.stderr or result.stdout}")
        csv_files = list(Path(tmp).glob("*.csv"))
        if not csv_files or csv_files[0].stat().st_size == 0:
            return pd.DataFrame(columns=[*OHLC, "volume"])
        return parse_dukascopy_csv(csv_files[0])


# ----------------------------------------------------------- lógica pura
def parse_dukascopy_csv(path: Path) -> pd.DataFrame:
    """CSV de dukascopy-node (timestamp ms epoch) → DataFrame con ts ISO UTC."""
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=[*OHLC, "volume"])
    ts = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.index = ts.dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df[[*OHLC, "volume"]]


def upsert_intraday(conn: sqlite3.Connection, symbol: str, side: str, df: pd.DataFrame) -> int:
    """Inserta/actualiza un lado (bid o ask) sin pisar el otro.

    Cada lado llega en una descarga distinta; la PK (symbol, ts) hace
    de punto de encuentro. El volumen solo lo escribe el lado bid
    (ambos lados traen tick volume casi idéntico; elegimos uno).
    """
    if side not in ("bid", "ask"):
        raise ValueError(f"side debe ser bid o ask, no {side!r}")
    if df.empty:
        return 0
    cols = [f"{side}_{c}" for c in OHLC]
    volume_update = ", volume = excluded.volume" if side == "bid" else ""
    rows = [
        (symbol, ts, r.open, r.high, r.low, r.close, r.volume if side == "bid" else None)
        for ts, r in df.iterrows()
        if pd.notna(r.close)
    ]
    conn.executemany(
        f"""
        INSERT INTO intraday_bars (symbol, ts, {", ".join(cols)}, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (symbol, ts) DO UPDATE SET
            {", ".join(f"{c} = excluded.{c}" for c in cols)}{volume_update}
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def intraday_incremental_start(conn: sqlite3.Connection, symbol: str) -> str:
    """Fecha (yyyy-mm-dd) desde la que descargar: última barra menos solape."""
    last = conn.execute(
        "SELECT MAX(ts) FROM intraday_bars WHERE symbol = ?", (symbol,)
    ).fetchone()[0]
    if last is None:
        return INTRADAY_START.get(symbol, DEFAULT_INTRADAY_START)
    last_day = date.fromisoformat(last[:10])
    return (last_day - timedelta(days=INTRADAY_OVERLAP_DAYS)).isoformat()


def intraday_dataset_hash(conn: sqlite3.Connection, symbol: str) -> str:
    """Reutiliza el mecanismo de hash del diario sobre la tabla intradía."""
    import hashlib

    h = hashlib.sha256()
    for row in conn.execute(
        "SELECT ts, bid_close, ask_close, volume FROM intraday_bars "
        "WHERE symbol = ? ORDER BY ts",
        (symbol,),
    ):
        h.update(repr(row).encode())
    return h.hexdigest()


def resample_bars(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Agrega barras OHLCV a un timeframe mayor (p. ej. 15m → 1h).

    Regla clásica: open = primero, high = máximo, low = mínimo,
    close = último, volume = suma.
    """
    if df.empty:
        return df
    out = df.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["close"])


def year_chunks(date_from: str, date_to: str) -> list[tuple[str, str]]:
    """Parte [date_from, date_to] en trozos por año natural.

    Un backfill de 11 años en una sola llamada es frágil: si falla al
    minuto 25 se pierde todo. Por trozos, cada año queda persistido al
    terminar y una re-ejecución continúa donde se quedó (incremental).
    """
    start = date.fromisoformat(date_from)
    end = date.fromisoformat(date_to)
    chunks = []
    while start < end:
        year_end = min(date(start.year + 1, 1, 1), end)
        chunks.append((start.isoformat(), year_end.isoformat()))
        start = year_end
    return chunks


# ------------------------------------------------------------ orquestación
def update_intraday(conn: sqlite3.Connection, symbol: str = "XAU") -> dict:
    """Actualización incremental bid + ask de un símbolo intradía.

    Por trozos anuales, y dentro de cada trozo se descargan AMBOS lados
    antes de escribir nada: nunca queda un rango con bid pero sin ask.
    """
    instrument = INTRADAY_SYMBOLS[symbol]
    start = intraday_incremental_start(conn, symbol)
    # -to es exclusivo → con la fecha de HOY descargamos hasta ayer 23:45.
    # El día en curso no se descarga: su fichero aún no existe en Dukascopy
    # (con -re eso aborta la descarga) y una vela de hoy a medias tampoco
    # sirve para research. Entra mañana vía el solape de 3 días.
    end = datetime.now(UTC).date().isoformat()
    total = 0
    if start >= end:
        log.info("intradia_ya_al_dia", symbol=symbol)
        return {"symbol": meta_key(symbol), "fetched_from": start, "rows_upserted": 0,
                "content_hash": intraday_dataset_hash(conn, symbol)}
    for chunk_start, chunk_end in year_chunks(start, end):
        for attempt in range(1, CHUNK_RETRIES + 1):
            try:
                frames = {
                    side: fetch_intraday(instrument, side, chunk_start, chunk_end)
                    for side in ("bid", "ask")
                }
                break
            except RuntimeError as exc:
                if attempt == CHUNK_RETRIES:
                    raise
                log.warning("chunk_reintento", desde=chunk_start, intento=attempt,
                            error=str(exc)[-200:])
                # Las ventanas de rechazo de Dukascopy duran minutos:
                # backoffs cortos reintentan dentro de la misma ventana
                time.sleep(90 * attempt)
        n = sum(upsert_intraday(conn, symbol, side, df) for side, df in frames.items())
        log.info("intradia_trozo", symbol=symbol, desde=chunk_start,
                 hasta=chunk_end, filas=n)
        total += n
    key = meta_key(symbol)
    content_hash = intraday_dataset_hash(conn, symbol)
    _touch_meta_intraday(conn, key, content_hash)
    return {"symbol": key, "fetched_from": start, "rows_upserted": total,
            "content_hash": content_hash}


def _touch_meta_intraday(conn: sqlite3.Connection, key: str, content_hash: str) -> None:
    conn.execute(
        """
        INSERT INTO dataset_meta (symbol, last_updated, content_hash) VALUES (?, ?, ?)
        ON CONFLICT (symbol) DO UPDATE SET
            last_updated = excluded.last_updated, content_hash = excluded.content_hash
        """,
        (key, datetime.now(UTC).isoformat(), content_hash),
    )
    conn.commit()


def load_intraday_ohlc(conn: sqlite3.Connection, symbol: str = "XAU",
                       start: str | None = None) -> pd.DataFrame:
    """Barras 15m OHLC en precio MID + spread + volumen, para estrategias.

    OHLC mid = media de los OHLC bid y ask. El spread por barra permite
    al backtest intradía cobrar el coste REAL del momento de cada trade
    (el spread de las 14:30 de un NFP no es el de una madrugada).
    """
    query = (
        "SELECT ts, (bid_open + ask_open) / 2 AS open, "
        "(bid_high + ask_high) / 2 AS high, "
        "(bid_low + ask_low) / 2 AS low, "
        "(bid_close + ask_close) / 2 AS close, "
        "ask_close - bid_close AS spread, volume "
        "FROM intraday_bars WHERE symbol = ? "
        "AND bid_close IS NOT NULL AND ask_close IS NOT NULL"
    )
    params: list = [symbol]
    if start:
        query += " AND ts >= ?"
        params.append(start)
    df = pd.read_sql(query + " ORDER BY ts", conn, params=params, index_col="ts")
    df.index = pd.to_datetime(df.index)
    return df


def load_intraday_mid(conn: sqlite3.Connection, symbol: str = "XAU",
                      start: str | None = None) -> pd.DataFrame:
    """Barras 15m como precio MID ((bid+ask)/2) + spread, indexadas por ts.

    El mid es el precio 'justo' para estadísticas: usar solo bid (o solo
    ask) sesga los retornos con los vaivenes del spread.
    """
    query = (
        "SELECT ts, (bid_close + ask_close) / 2 AS mid, "
        "ask_close - bid_close AS spread "
        "FROM intraday_bars WHERE symbol = ? "
        "AND bid_close IS NOT NULL AND ask_close IS NOT NULL"
    )
    params: list = [symbol]
    if start:
        query += " AND ts >= ?"
        params.append(start)
    df = pd.read_sql(query + " ORDER BY ts", conn, params=params, index_col="ts")
    df.index = pd.to_datetime(df.index)
    return df


def has_intraday_data(conn: sqlite3.Connection, symbol: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM intraday_bars WHERE symbol = ? LIMIT 1", (symbol,)
    ).fetchone()
    return row is not None


def main() -> None:
    """Backfill/actualización manual: python -m gold_bot.data.intraday"""
    from gold_bot.data.db import connect

    conn = connect()
    for symbol in INTRADAY_SYMBOLS:
        print(update_intraday(conn, symbol))


def intraday_summary(conn: sqlite3.Connection) -> list[dict]:
    """Resumen por símbolo intradía, mismo formato que data_summary()."""
    out = []
    for symbol, instrument in INTRADAY_SYMBOLS.items():
        n, first, last = conn.execute(
            "SELECT COUNT(*), MIN(ts), MAX(ts) FROM intraday_bars WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        meta = conn.execute(
            "SELECT last_updated, content_hash FROM dataset_meta WHERE symbol = ?",
            (meta_key(symbol),),
        ).fetchone()
        out.append({
            "symbol": f"{symbol} · 15m",
            "yahoo_ticker": f"dukascopy:{instrument}",
            "description": "Oro spot 15m bid/ask — spread real por barra",
            "rows": n,
            "first_date": first[:10] if first else None,
            "last_date": last[:10] if last else None,
            "last_updated": meta[0] if meta else None,
            "content_hash": meta[1] if meta else None,
        })
    return out


if __name__ == "__main__":
    main()
