"""Tests del pipeline intradía: merge bid/ask, incremental, chunks, resample.

Sin red: base en memoria y DataFrames sintéticos.
"""

import pandas as pd
import pytest

from gold_bot.data.db import connect
from gold_bot.data.intraday import (
    INTRADAY_HISTORY_START,
    INTRADAY_OVERLAP_DAYS,
    intraday_incremental_start,
    resample_bars,
    upsert_intraday,
    year_chunks,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def make_bars(ts_list: list[str], close: float = 2000.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 0.5,
        },
        index=ts_list,
    )


TS = ["2024-01-02T10:00:00", "2024-01-02T10:15:00"]


def test_bid_ask_merge_same_row(conn):
    upsert_intraday(conn, "XAU", "bid", make_bars(TS, close=2000.0))
    upsert_intraday(conn, "XAU", "ask", make_bars(TS, close=2000.4))
    rows = conn.execute(
        "SELECT bid_close, ask_close, volume FROM intraday_bars ORDER BY ts"
    ).fetchall()
    assert len(rows) == 2  # merge: 2 barras, no 4 filas
    assert rows[0] == (2000.0, 2000.4, 0.5)


def test_ask_does_not_overwrite_bid_volume(conn):
    upsert_intraday(conn, "XAU", "bid", make_bars(TS))
    ask = make_bars(TS, close=2000.4)
    ask["volume"] = 99.0  # el volumen del lado ask se ignora
    upsert_intraday(conn, "XAU", "ask", ask)
    vol = conn.execute("SELECT volume FROM intraday_bars LIMIT 1").fetchone()[0]
    assert vol == 0.5


def test_upsert_rejects_bad_side(conn):
    with pytest.raises(ValueError):
        upsert_intraday(conn, "XAU", "mid", make_bars(TS))


def test_incremental_start_empty(conn):
    assert intraday_incremental_start(conn, "XAU") == INTRADAY_HISTORY_START


def test_incremental_start_applies_overlap(conn):
    upsert_intraday(conn, "XAU", "bid", make_bars(["2024-06-10T22:45:00"]))
    expected = (
        pd.Timestamp("2024-06-10") - pd.Timedelta(days=INTRADAY_OVERLAP_DAYS)
    ).date().isoformat()
    assert intraday_incremental_start(conn, "XAU") == expected


def test_year_chunks_splits_by_year():
    chunks = year_chunks("2022-06-15", "2024-03-01")
    assert chunks == [
        ("2022-06-15", "2023-01-01"),
        ("2023-01-01", "2024-01-01"),
        ("2024-01-01", "2024-03-01"),
    ]


def test_year_chunks_single_range():
    assert year_chunks("2024-02-01", "2024-03-01") == [("2024-02-01", "2024-03-01")]


def test_resample_15m_to_1h():
    idx = pd.date_range("2024-01-02 10:00", periods=4, freq="15min")
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0, 4.0],
            "high": [10.0, 20.0, 30.0, 25.0],
            "low": [0.5, 1.5, 2.5, 3.5],
            "close": [1.5, 2.5, 3.5, 4.5],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=idx,
    )
    out = resample_bars(df, "1h")
    assert len(out) == 1
    row = out.iloc[0]
    assert row.open == 1.0  # primero
    assert row.high == 30.0  # máximo
    assert row.low == 0.5  # mínimo
    assert row.close == 4.5  # último
    assert row.volume == 4.0  # suma
