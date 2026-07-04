"""Almacenamiento local en SQLite.

Una sola base de datos (data/gold_bot.db) con:
  - bars: OHLCV diario por símbolo. PK (symbol, date) → un upsert
    incremental nunca duplica filas.
  - dataset_meta: por símbolo, cuándo se actualizó y el hash del
    contenido (regla de reproducibilidad: si dos backtests usan el
    mismo hash, usaron exactamente los mismos datos).

SQLite no necesita servidor y aguanta de sobra series diarias
(~5.000 filas/símbolo/20 años). Migraremos a PostgreSQL si algún
día hace falta concurrencia de verdad.
"""

import sqlite3
from pathlib import Path

from gold_bot.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,   -- ISO yyyy-mm-dd
    open   REAL NOT NULL,
    high   REAL NOT NULL,
    low    REAL NOT NULL,
    close  REAL NOT NULL,
    volume REAL,            -- NULL para series sin volumen (índices, yields)
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS dataset_meta (
    symbol       TEXT PRIMARY KEY,
    last_updated TEXT,      -- ISO datetime UTC
    content_hash TEXT       -- sha256 del contenido de bars para ese símbolo
);

-- Registro del runner diario de paper trading (Fase 7): una fila por
-- ejecución con la decisión completa — auditoría y tracking live.
CREATE TABLE IF NOT EXISTS live_log (
    ts           TEXT PRIMARY KEY,  -- ISO datetime UTC de la ejecución
    exposure     REAL,              -- fracción objetivo decidida por el sistema
    price        REAL,              -- mid XAU_USD en el momento
    balance      REAL,              -- balance de la cuenta
    currency     TEXT,
    held_units   REAL,              -- posición antes de operar
    target_units REAL,
    order_units  REAL,              -- 0 si no se ordenó nada
    dry_run      INTEGER NOT NULL DEFAULT 0
);

-- Barras intradía (15m) con BID y ASK en la misma fila: el spread real
-- de cada barra es ask_close - bid_close, sin joins. El volumen es
-- "tick volume" (nº de cambios de precio), no volumen negociado real:
-- en OTC (forex/metales spot) el volumen real no existe públicamente.
CREATE TABLE IF NOT EXISTS intraday_bars (
    symbol    TEXT NOT NULL,
    ts        TEXT NOT NULL,  -- ISO UTC yyyy-mm-ddTHH:MM:SS
    bid_open  REAL, bid_high REAL, bid_low REAL, bid_close REAL,
    ask_open  REAL, ask_high REAL, ask_low REAL, ask_close REAL,
    volume    REAL,
    PRIMARY KEY (symbol, ts)
);
"""


def default_db_path() -> Path:
    return settings.data_dir / "gold_bot.db"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Abre (y crea si no existe) la base de datos.

    Acepta ":memory:" para tests. Cada petición/hilo debe abrir su
    propia conexión: sqlite3 no comparte conexiones entre hilos.
    """
    path = db_path if db_path is not None else default_db_path()
    if isinstance(path, Path):
        path.parent.mkdir(parents=True, exist_ok=True)
    # timeout alto: si dos procesos escriben a la vez (p. ej. backfill en
    # curso + auto-update del backend) esperan el lock en vez de fallar
    conn = sqlite3.connect(path, timeout=30)
    conn.executescript(SCHEMA)
    return conn
