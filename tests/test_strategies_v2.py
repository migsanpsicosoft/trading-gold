"""Tests de las estrategias v2 (personalizadas por activo)."""

import numpy as np
import pandas as pd

from gold_bot.data.features import compute_asset_features
from gold_bot.strategies.base import IntradayData, StrategyData
from gold_bot.strategies.monthly_seasonality import MonthlySeasonality
from gold_bot.strategies.overnight_equity import OvernightEquity
from gold_bot.strategies.risk_off_jpy import RiskOffJPY
from gold_bot.strategies.st_reversal import ShortTermReversal
from gold_bot.strategies.ts_momentum import TSMomentum


def make_bars(closes, start="2018-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.005, "low": c * 0.995,
                         "close": c, "volume": 1.0})


def make_data(closes, start="2018-01-01"):
    bars = make_bars(closes, start)
    return StrategyData(bars=bars, features=compute_asset_features(bars))


# ------------------------------------------------------------- ts_momentum
def test_ts_momentum_follows_the_year():
    up = list(100 * np.exp(np.linspace(0, 0.5, 600)))  # subida sostenida
    pos = TSMomentum().generate_positions(make_data(up))
    assert (pos.dropna().iloc[100:] == 1.0).all()
    down = list(100 * np.exp(np.linspace(0, -0.5, 600)))
    pos = TSMomentum().generate_positions(make_data(down))
    assert (pos.dropna().iloc[100:] == -1.0).all()


def test_ts_momentum_rebalances_monthly():
    rng = np.random.default_rng(42)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 700))))
    pos = TSMomentum().generate_positions(make_data(closes))
    changes = (pos.diff().abs() > 1e-9).sum()
    assert changes < 25  # cambia como mucho una vez por ciclo de rebalanceo


def test_ts_momentum_truncation_invariant():
    rng = np.random.default_rng(42)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 700))))
    full = TSMomentum().generate_positions(make_data(closes))
    partial = TSMomentum().generate_positions(make_data(closes[:500]))
    pd.testing.assert_series_equal(full.iloc[:500], partial, check_freq=False)


# ------------------------------------------------------------- st_reversal
def test_st_reversal_fades_the_move():
    rng = np.random.default_rng(42)
    base = list(100 * np.exp(np.cumsum(rng.normal(0, 0.005, 100))))
    spike = [base[-1] * 1.06] * 3  # estirón del +6% en 5 días
    pos = ShortTermReversal().generate_positions(make_data(base + spike))
    assert pos.iloc[-1] < -0.5  # contra el estirón
    assert (pos.dropna().abs() <= 1.0).all()


# ---------------------------------------------------- monthly_seasonality
def test_monthly_seasonality_learns_a_month():
    # enero deriva +0.4%/día todos los años; el resto plano con ruido
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2012-01-01", periods=3000)
    ret = pd.Series(rng.normal(0, 0.0008, len(idx)), index=idx)
    ret[idx.month == 1] += 0.004
    closes = list(100 * np.exp(ret.cumsum()))
    pos = MonthlySeasonality().generate_positions(make_data(closes, "2012-01-01"))
    late = pos[pos.index.year >= 2021]
    january = late[late.index.month == 1].dropna()
    others = late[late.index.month != 1].dropna()
    assert (january == 1.0).mean() > 0.9  # descubre enero
    # con |t|>1.5 hay falsos positivos esperables (~15-19% por celda);
    # lo que no puede es activarse en los meses sin deriva al nivel de enero
    assert others.abs().mean() < 0.35


def test_monthly_seasonality_truncation_invariant():
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2012-01-01", periods=3000)
    ret = pd.Series(rng.normal(0.0002, 0.008, len(idx)), index=idx)
    closes = list(100 * np.exp(ret.cumsum()))
    full = MonthlySeasonality().generate_positions(make_data(closes, "2012-01-01"))
    partial = MonthlySeasonality().generate_positions(
        make_data(closes[:2000], "2012-01-01"))
    pd.testing.assert_series_equal(full.iloc[:2000], partial, check_freq=False)


# ------------------------------------------------------- overnight_equity
def test_overnight_holds_only_last_bar():
    idx = pd.date_range("2024-01-02 00:00", periods=96 * 3, freq="15min")
    c = pd.Series(5000.0, index=idx)
    bars = pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                         "spread": 0.5, "volume": 1.0})
    pos = OvernightEquity().generate_positions(IntradayData(bars))
    per_day = pos.groupby(pos.index.normalize()).sum()
    assert (per_day == 1.0).all()  # exactamente una barra al día
    last_bars = pos.groupby(pos.index.normalize()).last()
    assert (last_bars == 1.0).all()  # y es la última


# ---------------------------------------------------------- risk_off_jpy
def test_risk_off_jpy_follows_equity_momentum():
    bars = make_bars([150.0] * 100)
    features = compute_asset_features(bars)
    features["spx_ret_60d"] = pd.Series(
        [np.nan] * 10 + [0.05] * 50 + [-0.08] * 40, index=bars.index)
    pos = RiskOffJPY().generate_positions(StrategyData(bars=bars, features=features))
    assert (pos.iloc[10:60] == 1.0).all()   # risk-on → largo USDJPY
    assert (pos.iloc[60:] == -1.0).all()    # risk-off → corto (yen fuerte)
    assert pos.iloc[:10].isna().all()
