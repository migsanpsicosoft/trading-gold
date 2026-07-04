"""Tests del deflated Sharpe y los stress tests."""

import numpy as np
import pandas as pd

from gold_bot.backtest.deflated_sharpe import (
    deflated_sharpe,
    expected_max_sharpe_daily,
    probabilistic_sharpe,
)
from gold_bot.risk.stress import crisis_performance, drawdown_episodes, shock_table


def make_returns(mean: float, std: float, n: int = 1500, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n)
    return pd.Series(rng.normal(mean, std, n), index=idx)


def test_psr_high_for_strong_sharpe():
    # Sharpe anual ~2.4: PSR contra 0 debe ser ~1
    r = make_returns(0.0006, 0.004)
    assert probabilistic_sharpe(r, 0.0) > 0.99


def test_psr_half_for_zero_mean():
    r = make_returns(0.0, 0.004)
    psr = probabilistic_sharpe(r, 0.0)
    assert 0.2 < psr < 0.8  # alrededor de 0.5


def test_dsr_below_psr():
    """El DSR siempre exige más que el PSR (benchmark > 0 por multiple testing)."""
    r = make_returns(0.0003, 0.004)
    dsr = deflated_sharpe(r)["dsr"]
    psr = probabilistic_sharpe(r, 0.0)
    assert dsr < psr


def test_expected_max_sharpe_grows_with_trials():
    assert expected_max_sharpe_daily(100) > expected_max_sharpe_daily(10)


def test_drawdown_episodes_known_case():
    idx = pd.bdate_range("2020-01-01", periods=8)
    # sube, cae 2 días (~-4%), recupera; luego caída abierta al final
    ret = pd.Series([0.05, -0.02, -0.02, 0.05, 0.0, 0.03, -0.01, -0.01], index=idx)
    episodes = drawdown_episodes(ret, top=5)
    assert len(episodes) == 2
    worst = episodes[0]
    assert worst["depth"] < -0.035
    assert worst["days_to_recover"] is not None
    assert episodes[1]["days_to_recover"] is None  # el último sigue abierto


def test_crisis_windows_present():
    r = make_returns(0.0002, 0.004, n=1800)  # cubre 2019-2026
    crisis = crisis_performance(r)
    names = [c["name"] for c in crisis]
    assert "COVID crash" in names
    for c in crisis:
        assert c["max_dd"] <= 0


def test_shock_table_scales_with_exposure():
    table = shock_table(net_exposure=0.5)
    drop10 = next(t for t in table if t["gold_move"] == -0.10)
    assert drop10["portfolio_impact"] == -0.05
