"""COT (CFTC Commitments of Traders): posicionamiento semanal.

El informe semanal de la CFTC dice quién está posicionado en cada
futuro: no-comerciales (especuladores) vs comerciales (hedgers).
Documentado: los EXTREMOS de posicionamiento especulativo anticipan
reversiones (el último comprador ya compró).

ANTI-LOOKAHEAD (crítico): el informe es "as of" el MARTES pero se
publica el VIERNES a las 15:30 ET. Usarlo en su fecha as-of sería
mirar el futuro. COT_LAG_DAYS desplaza la disponibilidad al lunes
siguiente (conservador).

Fuente: ficheros anuales deacot{YYYY}.zip de cftc.gov (gratuitos).
"""

import io
import sqlite3
import zipfile
from datetime import UTC, datetime

import pandas as pd
import requests

from gold_bot.utils.log import get_logger

log = get_logger(__name__)

COT_URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
COT_FIRST_YEAR = 2005
COT_LAG_DAYS = 6  # martes as-of → disponible el lunes siguiente

# CFTC Contract Market Code por activo (verificados en deacot2024)
COT_CODES: dict[str, str] = {
    "XAU": "088691",   # GOLD - COMEX
    "XAG": "084691",   # SILVER - COMEX
    "HG": "085692",    # COPPER #1 - COMEX
    "WTI": "067651",   # WTI-PHYSICAL - NYMEX
    "NG": "023651",    # NAT GAS NYME
    "EUR": "099741",   # EURO FX - CME
    "JPY": "097741",   # JAPANESE YEN - CME
    "SPX": "13874A",   # E-MINI S&P 500 - CME
    "USB": "020601",   # UST BOND - CBT
}

_COLS = {
    "date": "As of Date in Form YYYY-MM-DD",
    "code": "CFTC Contract Market Code",
    "oi": "Open Interest (All)",
    "nc_long": "Noncommercial Positions-Long (All)",
    "nc_short": "Noncommercial Positions-Short (All)",
}


def download_cot_year(year: int) -> pd.DataFrame:
    """Descarga y parsea un año de COT → filas de nuestros activos."""
    r = requests.get(COT_URL.format(year=year), timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        name = zf.namelist()[0]
        df = pd.read_csv(zf.open(name), usecols=list(_COLS.values()),
                         dtype={_COLS["code"]: str}, low_memory=False)
    df.columns = ["mdate" if c == _COLS["date"] else c for c in df.columns]
    code_to_symbol = {v: k for k, v in COT_CODES.items()}
    df[_COLS["code"]] = df[_COLS["code"]].str.strip()
    df = df[df[_COLS["code"]].isin(code_to_symbol)]
    out = pd.DataFrame({
        "symbol": df[_COLS["code"]].map(code_to_symbol),
        "report_date": df["mdate"],
        "net_spec": (df[_COLS["nc_long"]] - df[_COLS["nc_short"]])
        / df[_COLS["oi"]].replace(0, pd.NA),
        "open_interest": df[_COLS["oi"]],
    })
    return out.dropna(subset=["net_spec"])


def upsert_cot(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    rows = [(r.symbol, r.report_date, float(r.net_spec), float(r.open_interest))
            for r in df.itertuples()]
    conn.executemany(
        "INSERT INTO cot (symbol, report_date, net_spec, open_interest) "
        "VALUES (?, ?, ?, ?) ON CONFLICT (symbol, report_date) DO UPDATE SET "
        "net_spec = excluded.net_spec, open_interest = excluded.open_interest",
        rows,
    )
    conn.commit()
    return len(rows)


def update_cot(conn: sqlite3.Connection) -> dict:
    """Incremental: descarga los años que faltan + siempre el año en curso."""
    last = conn.execute("SELECT MAX(report_date) FROM cot").fetchone()[0]
    current_year = datetime.now(UTC).year
    start_year = COT_FIRST_YEAR if last is None else int(last[:4])
    total = 0
    for year in range(start_year, current_year + 1):
        try:
            total += upsert_cot(conn, download_cot_year(year))
        except Exception as exc:
            log.error("cot_anno_fallo", anno=year, error=str(exc))
    log.info("cot_actualizado", filas=total)
    return {"rows_upserted": total}


def load_cot_daily(conn: sqlite3.Connection, symbol: str,
                   index: pd.DatetimeIndex) -> pd.Series:
    """net_spec como serie DIARIA alineada a `index`, con el lag de
    publicación aplicado: el dato del martes vale desde el lunes
    siguiente y se mantiene (ffill) hasta el informe siguiente."""
    rows = conn.execute(
        "SELECT report_date, net_spec FROM cot WHERE symbol = ? ORDER BY report_date",
        (symbol,),
    ).fetchall()
    if not rows:
        return pd.Series(dtype=float, index=index)
    s = pd.Series({pd.Timestamp(d) + pd.Timedelta(days=COT_LAG_DAYS): v
                   for d, v in rows})
    return s.reindex(index.union(s.index)).ffill().reindex(index)
