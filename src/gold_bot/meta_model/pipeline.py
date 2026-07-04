"""Pipeline completo del meta-modelo: datos → dataset → walk-forward → uplift.

Independiente de la capa API (la API lo cachea por versión de datos;
los scripts de estudio lo llaman directo).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from gold_bot.backtest.intraday import run_intraday_backtest
from gold_bot.backtest.simple import OOS_START, compute_metrics, run_backtest
from gold_bot.data.db import connect
from gold_bot.data.download import SYMBOLS, load_bars
from gold_bot.data.features import compute_features
from gold_bot.data.intraday import load_intraday_mid, load_intraday_ohlc
from gold_bot.meta_model.dataset import build_dataset, to_feature_matrix
from gold_bot.meta_model.model import walkforward_probs
from gold_bot.regime.hmm import walkforward_regimes
from gold_bot.strategies import INTRADAY_STRATEGIES, STRATEGIES
from gold_bot.strategies.base import IntradayData, StrategyData
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

TAKE_THRESHOLD = 0.5  # se toma la señal si P(éxito) >= 0.5
TRADING_DAYS = 252


@dataclass
class MetaInputs:
    bars: pd.DataFrame
    features: pd.DataFrame
    regimes: pd.DataFrame
    daily_positions: dict[str, pd.Series]
    daily_net: dict[str, pd.Series]  # retornos netos diarios por estrategia
    intraday_results: dict[str, tuple[pd.Series, pd.Series]]  # (pos_daily, net_daily)


def load_meta_inputs() -> MetaInputs:
    conn = connect()
    try:
        daily = {s: load_bars(conn, s) for s in SYMBOLS}
        features = compute_features(daily, load_intraday_mid(conn))
        bars15 = load_intraday_ohlc(conn)
    finally:
        conn.close()
    bars = daily["XAU"]
    regimes = walkforward_regimes(features)
    data = StrategyData(bars=bars, features=features)

    daily_positions = {
        name: strat.generate_positions(data) for name, strat in STRATEGIES.items()
    }
    spread = features.get("spread_mean")
    daily_net = {
        name: run_backtest(bars, pos, spread_usd=spread).net_returns
        for name, pos in daily_positions.items()
    }
    intraday_results = {}
    for name, strat in INTRADAY_STRATEGIES.items():
        pos15 = strat.generate_positions(IntradayData(bars15))
        result = run_intraday_backtest(bars15, pos15)
        intraday_results[name] = (result.positions, result.net_returns)

    return MetaInputs(bars, features, regimes, daily_positions, daily_net,
                      intraday_results)


def build_meta_dataset(inputs: MetaInputs,
                       label_mode: str = "strategy") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (dataset con y/ret/t1/strategy, X para el modelo)."""
    dataset = build_dataset(
        inputs.bars, inputs.features, inputs.regimes,
        inputs.daily_positions, inputs.intraday_results,
        label_mode=label_mode, daily_net=inputs.daily_net,
    )
    return dataset, to_feature_matrix(dataset)


def filter_daily_positions(positions: pd.Series, events_taken: pd.Series) -> pd.Series:
    """Reconstruye posiciones aplicando las decisiones del meta-modelo.

    events_taken: bool por fecha de evento (True = tomar la señal).
    Un evento rechazado deja la posición a 0 hasta el siguiente evento.
    """
    pos = positions.fillna(0.0)
    changed = pos.diff().abs() > 1e-9
    event_days = pos.index[changed]
    allowed = pd.Series(np.nan, index=pos.index)
    allowed[event_days] = 1.0
    rejected = events_taken[~events_taken].index
    allowed[allowed.index.isin(rejected)] = 0.0
    allowed = allowed.ffill().fillna(1.0)
    return pos * allowed


def evaluate_uplift(inputs: MetaInputs, dataset: pd.DataFrame,
                    probs: pd.Series, threshold: float = TAKE_THRESHOLD) -> list[dict]:
    """Sharpe OOS de cada estrategia antes y después del filtro meta.

    Solo cuentan las señales con predicción walk-forward (probs no NaN);
    las anteriores al primer fit se toman siempre (sin modelo no hay
    filtro — igual que ocurriría en producción).
    """
    spread = inputs.features.get("spread_mean")
    out = []

    for name, positions in inputs.daily_positions.items():
        mask = dataset["strategy"] == name
        p = probs[mask]
        taken = (p >= threshold) | p.isna()
        taken.index = dataset.index[mask]

        base = run_backtest(inputs.bars, positions, spread_usd=spread)
        filtered_pos = filter_daily_positions(positions, taken)
        filt = run_backtest(inputs.bars, filtered_pos, spread_usd=spread)

        decided = p.dropna()
        out.append({
            "strategy": name,
            "sharpe_before": base.metrics["oos"]["sharpe"],
            "sharpe_after": filt.metrics["oos"]["sharpe"],
            "signals_evaluated": int(len(decided)),
            "signals_taken_pct": float((decided >= threshold).mean()) if len(decided) else None,
        })

    for name, (_pos_daily, net_daily) in inputs.intraday_results.items():
        mask = dataset["strategy"] == name
        p = probs[mask]
        taken = (p >= threshold) | p.isna()
        taken.index = dataset.index[mask]

        net_filtered = net_daily.copy()
        rejected_days = taken[~taken].index
        net_filtered[net_filtered.index.isin(rejected_days)] = 0.0

        oos_before = compute_metrics(net_daily[net_daily.index >= OOS_START])
        oos_after = compute_metrics(net_filtered[net_filtered.index >= OOS_START])
        decided = p.dropna()
        out.append({
            "strategy": name,
            "sharpe_before": oos_before["sharpe"],
            "sharpe_after": oos_after["sharpe"],
            "signals_evaluated": int(len(decided)),
            "signals_taken_pct": float((decided >= threshold).mean()) if len(decided) else None,
        })

    return out


def run_meta_pipeline(refit_freq: str = "QE",
                      train_window_days: int | None = None) -> dict:
    """Pipeline completo. Devuelve dataset, X, probs walk-forward y uplift."""
    inputs = load_meta_inputs()
    dataset, x = build_meta_dataset(inputs)
    probs = walkforward_probs(x, dataset["y"], dataset["t1"],
                              refit_freq=refit_freq,
                              train_window_days=train_window_days)
    uplift = evaluate_uplift(inputs, dataset, probs)
    log.info("meta_pipeline", filas=len(dataset),
             con_prediccion=int(probs.notna().sum()))
    return {"inputs": inputs, "dataset": dataset, "x": x,
            "probs": probs, "uplift": uplift}
