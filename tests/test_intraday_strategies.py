"""Tests del motor intradía y las estrategias de 15m.

Los críticos: el gap nocturno NO se captura si la estrategia va plana
al cierre, y la agregación por barra → día es correcta.
"""

import numpy as np
import pandas as pd

from gold_bot.backtest.intraday import run_intraday_backtest
from gold_bot.strategies import INTRADAY_STRATEGIES
from gold_bot.strategies.base import IntradayData
from gold_bot.strategies.vol_breakout import VolBreakout
from gold_bot.strategies.vwap_reversion import VwapReversion


def make_bars15(closes: list[float], start: str = "2024-01-02 00:00",
                spread: float = 0.0, volume: float = 1.0) -> pd.DataFrame:
    """Barras de 15m consecutivas (96/día) con OHLC plano por barra."""
    idx = pd.date_range(start, periods=len(closes), freq="15min")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                         "spread": spread, "volume": volume})


# ------------------------------------------------------------------ motor
def test_overnight_gap_not_captured_when_flat():
    """Día 1 termina plano; el gap del +25% al día 2 no genera PnL."""
    day1 = [100.0] * 96
    day2 = [125.0] * 96  # gap nocturno enorme
    bars = make_bars15(day1 + day2)
    pos = pd.Series(1.0, index=bars.index)
    pos.iloc[:96] = 1.0
    pos.iloc[95] = 0.0   # plana en la última barra del día 1
    pos.iloc[96:] = 0.0  # día 2 fuera
    result = run_intraday_backtest(bars, pos)
    # sin posición viva en el gap ni movimiento intradía → PnL bruto 0,
    # solo costes de slippage por entrar/salir el día 1
    assert abs(result.net_returns.sum()) < 3e-4


def test_overnight_gap_captured_if_position_held():
    """Contraste: si la posición SIGUE viva en la última barra, el gap entra."""
    bars = make_bars15([100.0] * 96 + [125.0] * 96)
    pos = pd.Series(0.0, index=bars.index)
    pos.iloc[90:96] = 1.0  # vivo al cierre del día 1 (sin cerrar)
    result = run_intraday_backtest(bars, pos)
    assert result.net_returns.sum() > 0.2  # captura ~log(1.25)


def test_daily_aggregation():
    bars = make_bars15(list(np.linspace(100, 110, 96)) + list(np.linspace(110, 105, 96)))
    pos = pd.Series(1.0, index=bars.index)
    result = run_intraday_backtest(bars, pos)
    assert len(result.net_returns) == 2  # dos días
    assert result.net_returns.index[0].date().isoformat() == "2024-01-02"


# ------------------------------------------------------- vol breakout
def test_vol_breakout_rides_the_move():
    # 3 días de calentamiento con rango 2$, día 4 con subida de 10$
    quiet = [100.0 + (i % 8) * 0.25 for i in range(96)]
    burst = list(np.linspace(100, 110, 96))
    bars = make_bars15(quiet * 3 + burst)
    strat = VolBreakout(params={"k": 0.5, "range_window": 3})
    pos = strat.generate_positions(IntradayData(bars))
    day4 = pos.iloc[3 * 96:]
    assert day4.max() == 1.0          # rompió apertura + 0.5×rango → largo
    assert day4.iloc[-1] == 0.0        # plana al cierre
    assert pos.iloc[: 3 * 96].isna().all()  # calentamiento del rango → sin señal


def test_vol_breakout_flat_on_every_day_close():
    rng = np.random.default_rng(42)
    closes = list(2000 * np.exp(np.cumsum(rng.normal(0, 0.001, 96 * 10))))
    bars = make_bars15(closes)
    pos = VolBreakout(params={"k": 0.5, "range_window": 3}).generate_positions(
        IntradayData(bars)
    )
    last_bars = pos.groupby(pos.index.normalize()).last().dropna()
    assert (last_bars == 0.0).all()


# ------------------------------------------------------- vwap reversion
def test_vwap_reversion_buys_stretch_below():
    # 2 días estables de calentamiento (96 barras cada uno), luego un día
    # con caída brusca muy por debajo del VWAP y vuelta
    warmup_day = [100.0 + 0.05 * (i % 4) for i in range(96)]  # ruido leve: banda > 0
    event_day_bars = [100.0] * 60 + [97.0] * 10 + [100.0] * 26
    bars = make_bars15(warmup_day * 2 + event_day_bars)
    strat = VwapReversion(params={"entry_m": 2.0, "band_window": 100})
    pos = strat.generate_positions(IntradayData(bars))
    event_day = pos.iloc[2 * 96:]
    assert event_day.max() == 1.0      # compró el estirón bajista
    assert event_day.iloc[-1] == 0.0   # plana al cierre


def test_intraday_strategies_truncation_invariant():
    """Anti-leakage también en 15m: el futuro no cambia el pasado."""
    rng = np.random.default_rng(42)
    closes = list(2000 * np.exp(np.cumsum(rng.normal(0, 0.001, 96 * 8))))
    bars = make_bars15(closes)
    cut = 96 * 6
    for name, strat in INTRADAY_STRATEGIES.items():
        full = strat.generate_positions(IntradayData(bars)).iloc[:cut]
        partial = strat.generate_positions(IntradayData(bars.iloc[:cut]))
        pd.testing.assert_series_equal(full, partial, check_freq=False), name


def test_intraday_positions_bounded():
    rng = np.random.default_rng(42)
    closes = list(2000 * np.exp(np.cumsum(rng.normal(0, 0.001, 96 * 8))))
    bars = make_bars15(closes)
    for name, strat in INTRADAY_STRATEGIES.items():
        pos = strat.generate_positions(IntradayData(bars)).dropna()
        assert ((pos >= -1) & (pos <= 1)).all(), name
