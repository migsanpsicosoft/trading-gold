"""Ensemble con gating por régimen: la primera versión del libro completo.

Combina las 7 estrategias vivas a peso igual (1/N), cada una
multiplicada por su gate de régimen. El sizing por volatilidad y el
risk parity llegarán en los siguientes pasos de la Fase 5.
"""

import pandas as pd

from gold_bot.backtest.simple import OOS_START, compute_metrics, run_backtest
from gold_bot.meta_model.pipeline import MetaInputs
from gold_bot.risk.gating import gate_matrix


def ensemble_comparison(inputs: MetaInputs) -> dict:
    """Retornos del ensemble 1/N crudo vs con gating por régimen."""
    regime = inputs.regimes["regime"]
    spread = inputs.features.get("spread_mean")

    raw_nets: dict[str, pd.Series] = dict(inputs.daily_net)
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        raw_nets[name] = net_daily

    gates = gate_matrix(raw_nets, regime)

    gated_nets: dict[str, pd.Series] = {}
    for name, positions in inputs.daily_positions.items():
        # el gate del día t escala la posición decidida al cierre de t;
        # el motor la desplaza a t+1 (mismo tratamiento que la señal)
        gate = gates[name].reindex(positions.index).fillna(1.0)
        result = run_backtest(inputs.bars, positions * gate, spread_usd=spread)
        gated_nets[name] = result.net_returns
    for name, (_pos, net_daily) in inputs.intraday_results.items():
        # la intradía opera DURANTE t → solo puede usar el gate de t-1
        gate = gates[name].shift(1).reindex(net_daily.index).fillna(1.0)
        gated_nets[name] = net_daily * gate

    frame_raw = pd.DataFrame(raw_nets).reindex(regime.index)
    frame_gated = pd.DataFrame(gated_nets).reindex(regime.index)
    raw = frame_raw.mean(axis=1)
    gated = frame_gated.mean(axis=1)

    return {
        "raw": raw,
        "gated": gated,
        "gates": gates,
        "metrics": {
            "raw_oos": compute_metrics(raw[raw.index >= OOS_START]),
            "gated_oos": compute_metrics(gated[gated.index >= OOS_START]),
            "raw_full": compute_metrics(raw),
            "gated_full": compute_metrics(gated),
        },
    }
