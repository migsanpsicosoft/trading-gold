"""Tests del pipeline de datos: upsert, incremental, hash y staleness.

Sin red: base de datos en memoria y DataFrames sintéticos.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from gold_bot.data.db import connect
from gold_bot.data.download import (
    HISTORY_START,
    OVERLAP_DAYS,
    dataset_hash,
    incremental_start,
    is_stale,
    upsert_bars,
)


@pytest.fixture
def conn():
    c = connect(":memory:")
    yield c
    c.close()


def make_bars(dates: list[str], close: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "volume": 1000.0,
        },
        index=dates,
    )


def test_upsert_is_idempotent(conn):
    df = make_bars(["2024-01-01", "2024-01-02"])
    upsert_bars(conn, "XAU", df)
    upsert_bars(conn, "XAU", df)  # segunda pasada: mismas filas, no duplica
    n = conn.execute("SELECT COUNT(*) FROM bars WHERE symbol = 'XAU'").fetchone()[0]
    assert n == 2


def test_upsert_overwrites_corrections(conn):
    upsert_bars(conn, "XAU", make_bars(["2024-01-01"], close=100.0))
    upsert_bars(conn, "XAU", make_bars(["2024-01-01"], close=101.5))  # corrección de Yahoo
    close = conn.execute("SELECT close FROM bars WHERE symbol = 'XAU'").fetchone()[0]
    assert close == 101.5


def test_upsert_skips_nan_close(conn):
    df = make_bars(["2024-01-01", "2024-01-02"])
    df.loc["2024-01-02", "close"] = float("nan")
    assert upsert_bars(conn, "XAU", df) == 1


def test_incremental_start_empty_db(conn):
    assert incremental_start(conn, "XAU") == HISTORY_START


def test_incremental_start_with_data_applies_overlap(conn):
    upsert_bars(conn, "XAU", make_bars(["2024-06-10"]))
    expected = (pd.Timestamp("2024-06-10") - pd.Timedelta(days=OVERLAP_DAYS)).date().isoformat()
    assert incremental_start(conn, "XAU") == expected


def test_hash_changes_with_content(conn):
    upsert_bars(conn, "XAU", make_bars(["2024-01-01"], close=100.0))
    h1 = dataset_hash(conn, "XAU")
    upsert_bars(conn, "XAU", make_bars(["2024-01-02"], close=100.0))
    h2 = dataset_hash(conn, "XAU")
    assert h1 != h2


def test_hash_is_deterministic(conn):
    upsert_bars(conn, "XAU", make_bars(["2024-01-01", "2024-01-02"]))
    assert dataset_hash(conn, "XAU") == dataset_hash(conn, "XAU")


def test_is_stale_empty_db(conn):
    assert is_stale(conn) is True


def test_is_stale_respects_threshold(conn):
    fresh = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=48)).isoformat()

    from gold_bot.data.download import SYMBOLS

    for symbol in SYMBOLS:
        conn.execute(
            "INSERT INTO dataset_meta (symbol, last_updated, content_hash) VALUES (?, ?, 'x')",
            (symbol, fresh),
        )
    assert is_stale(conn) is False

    conn.execute("UPDATE dataset_meta SET last_updated = ? WHERE symbol = 'XAU'", (old,))
    assert is_stale(conn) is True
