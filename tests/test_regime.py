"""Tests del detector de régimen HMM.

El mundo sintético tiene regímenes conocidos por construcción (tramos
de vol baja/alta alternados): el HMM debe redescubrirlos sin etiquetas.
"""

import numpy as np
import pandas as pd
import pytest

from gold_bot.regime.hmm import (
    N_STATES,
    build_regime_matrix,
    filtered_probs,
    regime_stats,
    walkforward_regimes,
)


def make_features(n_days: int = 2200, seed: int = 42) -> pd.DataFrame:
    """Retornos con regímenes sintéticos: bloques de 120 días alternando
    vol 0.4% (calma) y vol 2.5% (turbulencia)."""
    rng = np.random.default_rng(seed)
    vols = []
    while len(vols) < n_days:
        vols += [0.004] * 120 + [0.025] * 120
    vols = np.array(vols[:n_days])
    ret = rng.normal(0, 1, n_days) * vols
    idx = pd.bdate_range("2005-01-03", periods=n_days)
    ret_s = pd.Series(ret, index=idx)
    vol20 = ret_s.rolling(20).std() * np.sqrt(252)
    return pd.DataFrame({"ret_1d": ret_s, "vol_20d": vol20}, index=idx)


@pytest.fixture(scope="module")
def regimes_and_features():
    features = make_features()
    regimes = walkforward_regimes(features, first_fit_year=2010)
    return features, regimes


def test_probs_are_valid(regimes_and_features):
    _, regimes = regimes_and_features
    probs = regimes[[f"prob_{i}" for i in range(N_STATES)]]
    assert not probs.isna().any().any()
    np.testing.assert_allclose(probs.sum(axis=1), 1.0, atol=1e-9)


def test_regimes_track_synthetic_vol(regimes_and_features):
    """Los días de vol alta sintética deben caer mayoritariamente en el
    estado de mayor vol (2) y los de vol baja en el menor (0)."""
    features, regimes = regimes_and_features
    vol = features["vol_20d"].reindex(regimes.index)
    high_vol_days = regimes["regime"][vol > 0.25]
    low_vol_days = regimes["regime"][vol < 0.10]
    assert (high_vol_days == N_STATES - 1).mean() > 0.7
    # con 3 estados y 2 regímenes reales, la calma se reparte entre los
    # estados 0 y 1 — lo que no puede es caer en turbulencia
    assert (low_vol_days < N_STATES - 1).mean() > 0.9


def test_truncation_invariance(regimes_and_features):
    """Anti-leakage: quitar el futuro no cambia los regímenes pasados
    (mismos fits de enero + forward solo hacia delante)."""
    features, full = regimes_and_features
    cutoff = "2012-12-31"
    truncated = walkforward_regimes(features[features.index <= cutoff],
                                    first_fit_year=2010)
    pd.testing.assert_frame_equal(
        full[full.index <= cutoff], truncated, check_freq=False
    )


def test_filtered_probs_only_look_back(regimes_and_features):
    """El forward con la MISMA serie más datos futuros no altera el pasado."""
    from hmmlearn.hmm import GaussianHMM

    from gold_bot.config import settings

    features, _ = regimes_and_features
    x = build_regime_matrix(features)
    xs = ((x - x.mean()) / x.std()).to_numpy()
    model = GaussianHMM(n_components=N_STATES, covariance_type="full",
                        n_iter=50, random_state=settings.random_seed)
    model.fit(xs[:1000])
    full = filtered_probs(model, xs[:1500])
    partial = filtered_probs(model, xs[:1200])
    np.testing.assert_allclose(full[:1200], partial, atol=1e-12)


def test_regime_stats_shape(regimes_and_features):
    features, regimes = regimes_and_features
    stats = regime_stats(features, regimes)
    assert len(stats) == N_STATES
    assert abs(sum(s["days_pct"] for s in stats) - 1.0) < 1e-9
    # el estado 2 (turbulencia) debe tener más vol que el 0 (calma)
    assert stats[2]["ann_vol"] > stats[0]["ann_vol"]
