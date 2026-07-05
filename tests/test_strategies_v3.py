"""Tests de las estrategias v3 (COT, carry, VIX) y del lag anti-lookahead."""

import numpy as np
import pandas as pd

from gold_bot.data.cot import COT_LAG_DAYS, load_cot_daily, upsert_cot
from gold_bot.data.db import connect
from gold_bot.strategies.base import StrategyData
from gold_bot.strategies.carry import CurveCarry, FxCarry
from gold_bot.strategies.cot_extreme import CotExtreme
from gold_bot.strategies.vix_structure import VixStructure


def make_bars(n=100, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n)
    c = pd.Series(100.0, index=idx)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0})


def data_with(bars, **features):
    f = pd.DataFrame(features, index=bars.index)
    return StrategyData(bars=bars, features=f)


# ------------------------------------------------------------ lag del COT
def test_cot_publication_lag():
    """El informe del martes NO puede estar disponible antes del lunes
    siguiente (viernes de publicación + margen)."""
    conn = connect(":memory:")
    report = pd.DataFrame([{"symbol": "XAU", "report_date": "2024-06-11",  # martes
                            "net_spec": 0.25, "open_interest": 100000.0}])
    upsert_cot(conn, report)
    idx = pd.bdate_range("2024-06-10", periods=10)
    daily = load_cot_daily(conn, "XAU", idx)
    available_from = pd.Timestamp("2024-06-11") + pd.Timedelta(days=COT_LAG_DAYS)
    assert daily[idx < available_from].isna().all()   # antes: nada
    assert (daily[idx >= available_from] == 0.25).all()  # después: ffill


# ------------------------------------------------------------ cot_extreme
def test_cot_extreme_contrarian():
    bars = make_bars(10)
    z = [0.0, 1.0, 2.5, 2.5, 1.0, 0.3, -2.5, -1.0, -0.2, 0.0]
    pos = CotExtreme().generate_positions(data_with(bars, cot_z=z))
    assert pos.iloc[2] == -1.0  # saturación de largos → corto
    assert pos.iloc[4] == -1.0  # se mantiene hasta normalizar
    assert pos.iloc[5] == 0.0   # |z| < 0.5 → fuera
    assert pos.iloc[6] == 1.0   # saturación de cortos → largo
    assert pos.iloc[8] == 0.0


# ------------------------------------------------------------------ carry
def test_fx_carry_deadband():
    bars = make_bars(4)
    pos = FxCarry().generate_positions(
        data_with(bars, carry_diff=[1.0, 0.1, -0.5, np.nan]))
    assert list(pos.iloc[:3]) == [1.0, 0.0, -1.0]
    assert pd.isna(pos.iloc[3])


def test_curve_carry_inversion_shorts():
    bars = make_bars(3)
    pos = CurveCarry().generate_positions(
        data_with(bars, curve_slope=[0.5, 0.05, -0.4]))
    assert list(pos) == [1.0, 0.0, -1.0]


# ---------------------------------------------------------- vix_structure
def test_vix_structure_contango_long():
    bars = make_bars(3)
    pos = VixStructure().generate_positions(
        data_with(bars, vix_ratio=[0.10, 0.005, -0.15]))
    assert list(pos) == [1.0, 0.0, -1.0]
