"""Tests del simulador de cuenta."""

import pandas as pd
import pytest

from gold_bot.execution.simulation import simulate_account


def make_inputs(closes: list[float], exposure: float = 1.0):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    bars = pd.DataFrame({"open": c, "high": c, "low": c, "close": c})
    return {
        "bars": bars,
        "spread_usd": pd.Series(0.0, index=idx),
        "net_exposure": pd.Series(exposure, index=idx),
        "intraday_contrib": pd.Series(0.0, index=idx),
        "brake": pd.Series(1.0, index=idx),
        "eurusd": pd.Series(1.0, index=idx),  # FX neutro para aritmética limpia
        "start": "2025-01-01",
        "end": "2025-12-31",
    }


def test_full_exposure_tracks_price():
    # 100% expuesto sin costes ni FX: +10% del oro → +~10% de la cuenta
    inputs = make_inputs([2000, 2000, 2200], exposure=1.0)
    sim = simulate_account(**inputs, capital_eur=5000)
    assert sim.summary["capital_final_eur"] == pytest.approx(5500, rel=0.01)


def test_rounding_to_big_step_zeroes_small_positions():
    # objetivo 0.3 oz con paso de 1 oz → posición redondeada a 0, sin PnL
    inputs = make_inputs([2000, 2000, 2200], exposure=0.12)  # 0.12×5000/2000=0.3oz
    sim = simulate_account(**inputs, capital_eur=5000, step_oz=1.0)
    assert sim.summary["capital_final_eur"] == pytest.approx(5000, abs=1)
    assert sim.summary["n_ordenes"] == 0


def test_costs_charged_per_order():
    inputs = make_inputs([2000, 2000, 2000], exposure=1.0)
    inputs["spread_usd"] = pd.Series(0.4, index=inputs["bars"].index)
    sim = simulate_account(**inputs, capital_eur=5000)
    # una orden inicial de 2.5 oz: coste = 2.5 × (0.2 + 0.2) = 1 €
    assert sim.summary["costes_totales_eur"] == pytest.approx(1.0, rel=0.05)


def test_eurusd_conversion():
    # oro +10% pero con EURUSD, el PnL en EUR se divide por el fx
    inputs = make_inputs([2000, 2000, 2200], exposure=1.0)
    inputs["eurusd"] = pd.Series(1.25, index=inputs["bars"].index)
    sim = simulate_account(**inputs, capital_eur=5000)
    # exposición objetivo en oz sube (5000€×1.25$/€/2000$) pero el PnL
    # vuelve a EUR entre 1.25 → neto: mismo +10% de la cuenta
    assert sim.summary["capital_final_eur"] == pytest.approx(5500, rel=0.01)
