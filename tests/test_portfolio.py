"""Tests de risk parity y vol targeting."""

import numpy as np
import pandas as pd

from gold_bot.risk.portfolio import (
    MAX_LEVERAGE,
    inverse_vol_weights,
    vol_target_leverage,
)


def make_nets(n: int = 400, seed: int = 42):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return {
        "tranquila": pd.Series(rng.normal(0.0002, 0.002, n), index=idx),  # vol baja
        "salvaje": pd.Series(rng.normal(0.0002, 0.02, n), index=idx),     # vol 10x
    }, idx


def test_inverse_vol_weights_favor_low_vol():
    nets, idx = make_nets()
    gates = pd.DataFrame(1.0, index=idx, columns=list(nets))
    w = inverse_vol_weights(nets, gates)
    late = w.iloc[100:]
    # pesos válidos: suman 1 y la estrategia tranquila pesa ~10x más
    np.testing.assert_allclose(late.sum(axis=1), 1.0, atol=1e-9)
    assert (late["tranquila"] > 0.85).all()


def test_gated_off_gets_zero_weight():
    nets, idx = make_nets()
    gates = pd.DataFrame(1.0, index=idx, columns=list(nets))
    gates.loc[idx[200:], "tranquila"] = 0.0
    w = inverse_vol_weights(nets, gates)
    assert (w["tranquila"].iloc[210:] == 0.0).all()
    np.testing.assert_allclose(w["salvaje"].iloc[210:], 1.0, atol=1e-9)


def test_all_gated_off_means_cash():
    nets, idx = make_nets()
    gates = pd.DataFrame(0.0, index=idx, columns=list(nets))
    w = inverse_vol_weights(nets, gates)
    assert (w.iloc[100:].sum(axis=1) == 0.0).all()


def test_leverage_hits_target_and_caps():
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", periods=600)
    # vol anual real ~4.8% → con objetivo 10% pediría ~2.1x → tope 2.0
    ret = pd.Series(rng.normal(0, 0.003, 600), index=idx)
    lev = vol_target_leverage(ret, target_vol=0.10)
    assert lev.max() <= MAX_LEVERAGE + 1e-9
    # con objetivo 2% (menos que la vol real) el apalancamiento es < 1
    lev_low = vol_target_leverage(ret, target_vol=0.02)
    assert lev_low.iloc[100:].mean() < 1.0


def test_drawdown_brake_caps_losses():
    from gold_bot.risk.portfolio import drawdown_brake

    idx = pd.bdate_range("2020-01-01", periods=60)
    # caída continua del 1% diario: sin freno el DD llegaría a ~-45%
    ret = pd.Series(-0.01, index=idx)
    braked, mult = drawdown_brake(ret, soft=-0.08, hard=-0.15)
    equity = np.exp(braked.cumsum())
    dd = equity / equity.cummax() - 1
    assert dd.min() > -0.16  # el freno corta cerca del límite duro
    assert mult.iloc[-1] < 0.01  # exposición prácticamente cortada
    assert mult.iloc[0] == 1.0  # empieza a plena exposición


def test_drawdown_brake_recovers():
    from gold_bot.risk.portfolio import drawdown_brake

    idx = pd.bdate_range("2020-01-01", periods=120)
    ret = pd.Series([-0.012] * 12 + [0.012] * 108, index=idx)
    braked, mult = drawdown_brake(ret, soft=-0.08, hard=-0.15)
    assert mult.iloc[13] < 1.0   # frenó durante la caída
    assert mult.iloc[-1] == 1.0  # recuperado el pico, exposición plena


def test_leverage_only_uses_past():
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2020-01-01", periods=600)
    ret = pd.Series(rng.normal(0, 0.005, 600), index=idx)
    full = vol_target_leverage(ret)
    partial = vol_target_leverage(ret.iloc[:400])
    pd.testing.assert_series_equal(full.iloc[:400], partial, check_freq=False)
