"""Tests del motor de backtest y del framework de estrategias.

El test crítico es test_signal_cannot_trade_same_day: una señal del
día t NO puede capturar el retorno del propio día t.
"""

import numpy as np
import pandas as pd
import pytest

from gold_bot.backtest.simple import (
    FALLBACK_SPREAD,
    compute_metrics,
    run_backtest,
)
from gold_bot.strategies import STRATEGIES
from gold_bot.strategies.base import StrategyData


def make_bars(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0})


def test_signal_cannot_trade_same_day():
    """Día 2 sube +10%. Señal emitida AL CIERRE del día 2 no puede capturarlo."""
    bars = make_bars([100, 110, 110, 110])
    positions = pd.Series([0.0, 1.0, 0.0, 0.0], index=bars.index)  # señal solo el día 2
    result = run_backtest(bars, positions, spread_usd=pd.Series(0.0, index=bars.index))
    # el +10% ocurre del día 1 al 2; la posición entra el día 3, donde el
    # retorno es 0 → PnL bruto = 0. Solo queda el slippage de entrar y salir.
    slippage_round_trip = 2 * 1.0 / 10_000
    assert result.net_returns.sum() == pytest.approx(-slippage_round_trip)


def test_constant_long_tracks_asset():
    """Posición +1 constante sin costes = retorno log del activo."""
    bars = make_bars([100, 105, 103, 108, 112])
    positions = pd.Series(1.0, index=bars.index)
    result = run_backtest(bars, positions, spread_usd=pd.Series(0.0, index=bars.index))
    # pos efectiva [0,1,1,1,1]: captura todos los retornos (el primero es
    # NaN); solo paga el slippage de la entrada inicial
    expected = np.log(112 / 100) - 1.0 / 10_000
    assert result.net_returns.sum() == pytest.approx(expected)


def test_costs_charged_on_position_changes():
    bars = make_bars([100.0] * 5)  # precio plano: todo el PnL son costes
    positions = pd.Series([1.0, 1.0, -1.0, -1.0, -1.0], index=bars.index)
    spread = pd.Series(0.5, index=bars.index)  # 0.5$ → 0.25$ por lado = 25 pb
    result = run_backtest(bars, positions, spread_usd=spread)
    # cambios de posición efectiva: 0→1 (|Δ|=1) y 1→-1 (|Δ|=2) → turnover 3
    half_spread_pct = 0.5 / 100 / 2
    slippage = 1.0 / 10_000
    expected_cost = 3 * (half_spread_pct + slippage)
    assert -result.net_returns.sum() == pytest.approx(expected_cost)


def test_fallback_spread_when_missing():
    bars = make_bars([100.0] * 3)
    positions = pd.Series([1.0, 1.0, 1.0], index=bars.index)
    result = run_backtest(bars, positions, spread_usd=None)
    expected_cost = 1 * (FALLBACK_SPREAD / 100 / 2 + 1.0 / 10_000)
    assert -result.net_returns.sum() == pytest.approx(expected_cost)


def test_max_drawdown_known_case():
    # equity 1.0 → 1.2 → 0.9 → 1.1: DD máximo = 0.9/1.2 - 1 = -25%
    r = pd.Series(np.log([1.2 / 1.0, 0.9 / 1.2, 1.1 / 0.9]),
                  index=pd.bdate_range("2024-01-01", periods=3))
    m = compute_metrics(pd.concat([r] * 10))  # repetido para pasar el mínimo de días
    assert m["max_drawdown"] == pytest.approx(-0.25, rel=1e-6)


# ------------------------------------------------------------- estrategias
@pytest.fixture
def strategy_data():
    from gold_bot.data.features import compute_features

    rng = np.random.default_rng(42)
    n = 400
    closes = list(2000 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n))))
    bars = make_bars(closes, start="2022-01-01")
    features = compute_features({"XAU": bars})
    return StrategyData(bars=bars, features=features)


def test_all_strategies_emit_valid_positions(strategy_data):
    for name, strat in STRATEGIES.items():
        pos = strat.generate_positions(strategy_data)
        assert (pos.index == strategy_data.bars.index).all(), name
        valid = pos.dropna()
        assert ((valid >= -1) & (valid <= 1)).all(), name
        assert len(valid) > 100, f"{name}: demasiados NaN"


def test_breakout_enters_and_exits():
    from gold_bot.strategies.breakout import Breakout

    # 80 días planos → subida fuerte 30 días → desplome
    closes = [100.0] * 80 + list(np.linspace(101, 140, 30)) + list(np.linspace(138, 90, 15))
    bars = make_bars(closes)
    pos = Breakout(params={"entry": 55, "exit": 20}).generate_positions(
        StrategyData(bars=bars, features=pd.DataFrame(index=bars.index))
    )
    assert pos.iloc[85] == 1.0  # rompió el máximo de 55d → largo
    assert pos.iloc[-1] in (-1.0, 0.0)  # el desplome lo saca (y puede girarlo)
    assert pos.iloc[79] == 0.0  # plano: sin ruptura, fuera


def test_mean_reversion_buys_the_dip():
    from gold_bot.strategies.mean_reversion import MeanReversion

    # precio estable con caída brusca del 8% y recuperación
    closes = [100.0 + 0.1 * (i % 5) for i in range(60)] + [92.0, 92.5] + [100.0] * 10
    bars = make_bars(closes)
    pos = MeanReversion().generate_positions(
        StrategyData(bars=bars, features=pd.DataFrame(index=bars.index))
    )
    assert pos.iloc[60] == 1.0  # el desplome estira el z por debajo de -2 → largo
    assert pos.iloc[-1] == 0.0  # recuperada la media → fuera


def test_strategies_are_truncation_invariant(strategy_data):
    """Anti-leakage: recortar el futuro no cambia las posiciones pasadas."""
    from gold_bot.data.features import compute_features

    cut = 300
    bars_cut = strategy_data.bars.iloc[:cut]
    data_cut = StrategyData(bars=bars_cut, features=compute_features({"XAU": bars_cut}))
    for name, strat in STRATEGIES.items():
        full = strat.generate_positions(strategy_data).iloc[:cut]
        partial = strat.generate_positions(data_cut)
        pd.testing.assert_series_equal(full, partial, check_freq=False), name
