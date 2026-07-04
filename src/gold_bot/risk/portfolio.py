"""Construcción de cartera: gating → risk parity → vol targeting.

Capas, cada una encima de la anterior:

  1. GATING por régimen (gating.py): qué estrategias están vivas hoy.
  2. RISK PARITY: peso ∝ 1/vol_60d de cada estrategia viva (con
     shift(1)). 1/N reparte capital; esto reparte RIESGO — una
     estrategia con vol 20% ya no domina a una con vol 5%.
  3. VOL TARGETING: apalancamiento L = vol_objetivo / vol_realizada_20d
     de la cartera (shift(1)), con tope MAX_LEVERAGE. Sube exposición
     cuando el sistema está tranquilo y des-apalanca solo cuando la
     volatilidad se dispara.

Netting: las estrategias diarias operan todas XAU → sus posiciones
ponderadas se suman en UNA posición combinada que pasa por el motor:
los costes se pagan sobre la posición NETA, como en el broker real.
Las intradía (cierran en el día) no pueden netearse con las diarias;
sus retornos netos se escalan por su peso (aproximación conservadora:
sus costes ya están dentro y escalan proporcionalmente).
"""

import numpy as np
import pandas as pd

from gold_bot.backtest.simple import OOS_START, compute_metrics, run_backtest
from gold_bot.meta_model.pipeline import MetaInputs
from gold_bot.risk.gating import gate_matrix

TARGET_VOL = 0.10          # vol anual objetivo de la cartera (decisión de riesgo)
MAX_LEVERAGE = 2.0         # tope duro de apalancamiento
STRAT_VOL_LOOKBACK = 60    # vol de cada estrategia para risk parity
PORT_VOL_LOOKBACK = 20     # vol de la cartera para el targeting
TRADING_DAYS = 252

# Freno de drawdown (límite duro): exposición plena hasta BRAKE_SOFT de
# DD; reducción lineal hasta 0 en BRAKE_HARD. Protege del punto débil
# del vol targeting: la vol realizada va con retraso en shocks rápidos.
# Config B elegida por Miguel (2026-07-04): vol 10% + freno -6/-12 →
# OOS sharpe 0.80, CAGR 8.2%, DD -14.6% (cumple el límite de -15%).
BRAKE_SOFT = -0.06
BRAKE_HARD = -0.12


def inverse_vol_weights(nets: dict[str, pd.Series], gates: pd.DataFrame) -> pd.DataFrame:
    """Pesos risk parity (suman 1 entre las estrategias con gate ON).

    Vol de 60 días con shift(1): el peso de hoy usa solo vol pasada.
    Estrategia sin historia de vol o con gate OFF → peso 0. Días sin
    ninguna activa → todos 0 (cartera en cash).
    """
    vols = pd.DataFrame({
        name: net.reindex(gates.index)
        .rolling(STRAT_VOL_LOOKBACK, min_periods=STRAT_VOL_LOOKBACK // 2)
        .std()
        .shift(1)
        for name, net in nets.items()
    })
    inv = (1.0 / vols).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    inv = inv * gates.reindex(columns=inv.columns).fillna(0.0)
    total = inv.sum(axis=1)
    weights = inv.div(total.where(total > 0, np.nan), axis=0).fillna(0.0)
    return weights


def vol_target_leverage(portfolio_ret: pd.Series,
                        target_vol: float = TARGET_VOL,
                        max_leverage: float = MAX_LEVERAGE) -> pd.Series:
    """L_t = vol_objetivo / vol_realizada(20d, shift 1), recortado."""
    realized = portfolio_ret.rolling(
        PORT_VOL_LOOKBACK, min_periods=PORT_VOL_LOOKBACK
    ).std().shift(1) * np.sqrt(TRADING_DAYS)
    lev = (target_vol / realized).clip(upper=max_leverage).fillna(1.0)
    return lev.replace([np.inf, -np.inf], max_leverage)


def drawdown_brake(returns: pd.Series, soft: float = BRAKE_SOFT,
                   hard: float = BRAKE_HARD,
                   peak_window: int = 252) -> tuple[pd.Series, pd.Series]:
    """Freno de drawdown secuencial (día a día, sin mirar el futuro).

    El multiplicador del día t sale del drawdown de la equity FRENADA
    al cierre de t-1, medido contra su PICO MÓVIL de `peak_window`
    días — no contra el máximo histórico. Con pico absoluto, un mal
    episodio deja el sistema en coma permanente (m≈0 → equity
    congelada → DD congelado → nunca vuelve); con pico móvil, la
    referencia 'olvida' y el sistema se rehabilita en ≤1 año.

    Aproximación de costes: multiplica retornos netos (los costes
    escalan ≈ linealmente con la exposición); el error es de segundo
    orden y conservador de revisar en la Fase 6.
    """
    r = returns.fillna(0.0).to_numpy()
    n = len(r)
    mult = np.ones(n)
    braked = np.zeros(n)
    log_eq = np.zeros(n + 1)  # log-equity frenada; [0]=0 es el arranque
    m = 1.0
    for i in range(n):
        mult[i] = m
        braked[i] = r[i] * m
        log_eq[i + 1] = log_eq[i] + braked[i]
        peak = log_eq[max(0, i + 1 - peak_window): i + 2].max()
        dd = float(np.exp(log_eq[i + 1] - peak) - 1)
        if dd >= soft:
            m = 1.0
        elif dd <= hard:
            m = 0.0
        else:
            m = (dd - hard) / (soft - hard)
    return (pd.Series(braked, index=returns.index),
            pd.Series(mult, index=returns.index))


def build_portfolio(inputs: MetaInputs,
                    target_vol: float = TARGET_VOL) -> dict:
    """Cartera completa por capas. Devuelve retornos y diagnósticos."""
    regime = inputs.regimes["regime"]
    idx = regime.index
    spread = inputs.features.get("spread_mean")

    nets: dict[str, pd.Series] = dict(inputs.daily_net)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        nets[name] = net_daily

    gates = gate_matrix(nets, regime)
    weights = inverse_vol_weights(nets, gates)

    # --- capa risk parity (pre-apalancamiento), con netting de las diarias
    combined_daily_pos = pd.Series(0.0, index=inputs.bars.index)
    for name, positions in inputs.daily_positions.items():
        w = weights[name].reindex(positions.index).fillna(0.0)
        combined_daily_pos = combined_daily_pos.add(
            positions.fillna(0.0) * w, fill_value=0.0
        )
    daily_result = run_backtest(inputs.bars, combined_daily_pos, spread_usd=spread)
    parity_ret = daily_result.net_returns.reindex(idx).fillna(0.0)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        w = weights[name].shift(1)  # la intradía opera DURANTE el día → peso de t-1
        parity_ret = parity_ret.add(
            (net_daily.reindex(idx) * w.reindex(idx)).fillna(0.0), fill_value=0.0
        )

    # --- capa vol targeting: escala las posiciones (y por tanto los costes)
    leverage = vol_target_leverage(parity_ret, target_vol)
    lev_daily = leverage.reindex(inputs.bars.index).fillna(1.0)
    final_daily = run_backtest(
        inputs.bars, combined_daily_pos * lev_daily, spread_usd=spread
    )
    final_ret = final_daily.net_returns.reindex(idx).fillna(0.0)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        w = weights[name].shift(1) * leverage.shift(1)
        final_ret = final_ret.add(
            (net_daily.reindex(idx) * w.reindex(idx)).fillna(0.0), fill_value=0.0
        )

    # --- capa límites duros: freno de drawdown
    braked_ret, brake_mult = drawdown_brake(final_ret)

    return {
        "parity_returns": parity_ret,
        "final_returns": braked_ret,
        "unbraked_returns": final_ret,
        "weights": weights,
        "leverage": leverage,
        "brake": brake_mult,
        "net_exposure": (combined_daily_pos * lev_daily).reindex(idx)
        * brake_mult.reindex(idx),
        "metrics": {
            "parity_oos": compute_metrics(parity_ret[parity_ret.index >= OOS_START]),
            "unbraked_oos": compute_metrics(final_ret[final_ret.index >= OOS_START]),
            "final_oos": compute_metrics(braked_ret[braked_ret.index >= OOS_START]),
            "final_full": compute_metrics(braked_ret),
        },
    }
