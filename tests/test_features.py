"""Tests de las features: correctitud de indicadores y AUSENCIA DE LEAKAGE.

El test más importante es test_no_leakage: añadir datos futuros no puede
cambiar ninguna feature del pasado. Si un día refactorizamos y ese test
rompe, hemos metido look-ahead bias.
"""

import numpy as np
import pandas as pd
import pytest

from gold_bot.data.features import (
    atr,
    compute_features,
    intraday_daily_stats,
    log_returns,
    realized_vol,
    rolling_zscore,
    rsi,
)


def make_ohlc(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 100.0})


@pytest.fixture
def daily():
    rng = np.random.default_rng(42)  # seed del proyecto
    n = 300
    xau = make_ohlc(list(2000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))))
    xag = make_ohlc(list(25 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))))
    dxy = make_ohlc(list(100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))))
    return {"XAU": xau, "XAG": xag, "DXY": dxy}


# ------------------------------------------------------------ indicadores
def test_log_returns_known_value():
    s = pd.Series([100.0, 110.0])
    assert log_returns(s).iloc[-1] == pytest.approx(np.log(1.1))


def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 200, 50))  # solo subidas
    down = pd.Series(np.linspace(200, 100, 50))  # solo bajadas
    assert rsi(up).iloc[-1] > 99
    assert rsi(down).iloc[-1] < 1


def test_atr_constant_range():
    # rango constante de 2$ sin gaps → ATR converge a 2
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.0, "volume": 1.0}, index=range(100))
    assert atr(df).iloc[-1] == pytest.approx(2.0, rel=1e-3)


def test_realized_vol_zero_for_constant_price():
    ret = log_returns(pd.Series([100.0] * 50))
    assert realized_vol(ret).iloc[-1] == pytest.approx(0.0)


def test_rolling_zscore_uses_only_window():
    s = pd.Series([1.0] * 60 + [2.0])
    z = rolling_zscore(s, window=60)
    # la ventana incluye el propio salto (59 unos + un dos) → z grande pero finito
    assert z.iloc[-1] > 5
    assert z.iloc[-2] != z.iloc[-2] or z.iloc[-2] == 0  # ventana constante → 0 o NaN


def test_intraday_daily_stats():
    idx = pd.to_datetime(
        ["2024-01-02 10:00", "2024-01-02 10:15", "2024-01-02 10:30",
         "2024-01-03 10:00", "2024-01-03 10:15"]
    )
    df = pd.DataFrame({"mid": [2000.0, 2002.0, 2001.0, 2010.0, 2010.0],
                       "spread": [0.3, 0.5, 0.4, 0.2, 0.2]}, index=idx)
    out = intraday_daily_stats(df)
    assert list(out.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert out.loc["2024-01-02", "spread_mean"] == pytest.approx(0.4)
    assert out.loc["2024-01-03", "rv_intraday"] >= 0


# ------------------------------------------------------------- ensamblado
def test_compute_features_columns_and_index(daily):
    f = compute_features(daily)
    assert list(f.index) == list(daily["XAU"].index)  # calendario del oro
    for col in ("ret_1d", "vol_20d", "rsi_14", "xau_xag_ratio", "corr_dxy_20d"):
        assert col in f.columns
    assert "us10y_chg_5d" not in f.columns  # no pasamos US10Y → no aparece


def test_no_leakage(daily):
    """LA prueba: datos futuros no cambian las features del pasado."""
    full = compute_features(daily)
    truncated = {k: v.iloc[:200] for k, v in daily.items()}
    partial = compute_features(truncated)
    pd.testing.assert_frame_equal(full.iloc[:200], partial, check_freq=False)


def test_no_leakage_intraday(daily):
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-01", periods=2000, freq="15min")
    intra = pd.DataFrame(
        {"mid": 2000 * np.exp(np.cumsum(rng.normal(0, 0.0005, 2000))),
         "spread": rng.uniform(0.2, 0.6, 2000)},
        index=idx,
    )
    full = compute_features(daily, intra)
    partial = compute_features(daily, intra.iloc[:1000])
    cutoff = intra.index[999].normalize() - pd.Timedelta(days=1)  # último día completo
    cols = ["rv_intraday", "spread_mean"]
    pd.testing.assert_frame_equal(
        full.loc[:cutoff, cols], partial.loc[:cutoff, cols], check_freq=False
    )
