"""Tests del gating adaptativo por régimen."""

import numpy as np
import pandas as pd

from gold_bot.risk.gating import MIN_REGIME_DAYS, conditional_gate


def make_world(n: int = 1200, seed: int = 42):
    """Regímenes alternos de 100 días; la estrategia GANA en régimen 0
    (+10 pb/día de media) y PIERDE en régimen 1 (−10 pb/día)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    regime = pd.Series([(i // 100) % 2 for i in range(n)], index=idx)
    drift = np.where(regime == 0, 0.001, -0.001)
    net = pd.Series(drift + rng.normal(0, 0.004, n), index=idx)
    return net, regime


def test_gate_learns_the_habitat():
    net, regime = make_world()
    gate = conditional_gate(net, regime)
    # tras el aprendizaje, ON en régimen 0 y OFF en régimen 1
    late = gate.iloc[600:]
    late_regime = regime.iloc[600:]
    assert (late[late_regime == 0] == 1.0).mean() > 0.9
    assert (late[late_regime == 1] == 0.0).mean() > 0.9


def test_gate_neutral_without_history():
    net, regime = make_world()
    gate = conditional_gate(net, regime)
    # los primeros días de cada régimen (sin MIN_REGIME_DAYS de historia)
    # son neutros = 1
    assert (gate.iloc[:MIN_REGIME_DAYS] == 1.0).all()


def test_gate_only_uses_past():
    """Truncar el futuro no cambia los gates pasados."""
    net, regime = make_world()
    full = conditional_gate(net, regime)
    cut = 800
    partial = conditional_gate(net.iloc[:cut], regime.iloc[:cut])
    pd.testing.assert_series_equal(full.iloc[:cut], partial, check_freq=False)


def test_gate_binary():
    net, regime = make_world()
    gate = conditional_gate(net, regime)
    assert set(gate.unique()) <= {0.0, 1.0}
