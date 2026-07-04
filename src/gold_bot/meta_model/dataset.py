"""Construcción del dataset del meta-modelo.

Cada fila = una señal de una estrategia. El meta-modelo aprende
P(la señal funciona | contexto del mercado en ese momento).

Dos tipos de evento:
  - Estrategias DIARIAS: el día t0 en que la posición objetivo cambia
    a un valor != 0 (entrada o giro). Features al cierre de t0 (la
    señal se decide con ese cierre). Etiqueta: triple barrier desde t0.
  - Estrategias INTRADÍA (operan y cierran dentro del día): el evento
    es "dejar operar a la estrategia el día t0". La decisión se toma
    ANTES de que t0 empiece → features del cierre de t0-1 (un lag
    extra, crítico contra el leakage). Etiqueta: PnL neto del día.

El régimen del HMM entra como features prob_0/1/2 — filtradas y
walk-forward, así que son legales en cada t0 por construcción.
"""

import numpy as np
import pandas as pd

from gold_bot.meta_model.labeling import BarrierConfig, triple_barrier_labels

BASE_FEATURES = [
    "ret_5d", "ret_20d", "vol_20d", "atr_14_pct", "rsi_14",
    "sma_ratio_20", "sma_ratio_50", "sma_ratio_200",
    "xau_xag_z60", "corr_dxy_20d", "dxy_ret_20d", "us10y_chg_5d",
    "tip_ret_20d", "rv_intraday", "spread_mean",
]
REGIME_FEATURES = ["prob_0", "prob_1", "prob_2"]


def daily_entry_events(positions: pd.Series) -> pd.DataFrame:
    """Días en que la posición objetivo cambia a un valor != 0."""
    pos = positions.fillna(0.0)
    changed = pos.diff().abs() > 1e-9
    entries = pos[changed & (pos.abs() > 1e-9)]
    return pd.DataFrame({"side": np.sign(entries)}, index=entries.index)


def intraday_day_events(positions_daily: pd.Series,
                        net_daily: pd.Series) -> pd.DataFrame:
    """Días en que la estrategia intradía operó, con su resultado neto."""
    traded = positions_daily.abs() > 1e-9
    days = positions_daily[traded].index
    return pd.DataFrame({
        "side": np.sign(positions_daily[traded]),
        "day_net": net_daily.reindex(days),
    }, index=days)


def strategy_outcome_labels(events: pd.DataFrame, strategy_net: pd.Series,
                            horizon: int = 10) -> pd.DataFrame:
    """Etiqueta alineada con la estrategia: ¿su PnL neto de los próximos
    `horizon` días hábiles fue positivo?

    Justificación a priori (documentada ANTES de ver resultados v2): la
    tabla de Sharpe por régimen (F3) demuestra que el rendimiento DE LAS
    ESTRATEGIAS es predecible por contexto; el triple barrier etiqueta
    otra cosa (toques de barrera del precio del oro) mucho más ruidosa
    — y su AUC walk-forward salió 0.50-0.52 (sin skill).
    """
    idx = strategy_net.index
    out = []
    for t0 in events.index:
        if t0 not in idx:
            continue
        pos0 = idx.get_loc(t0)
        window = strategy_net.iloc[pos0 + 1: pos0 + 1 + horizon]
        if len(window) < horizon:
            continue  # sin ventana completa no hay etiqueta
        ret = float(window.sum())
        out.append({"t0": t0, "y": int(ret > 0), "ret": ret,
                    "t1": window.index[-1], "side": float(events.loc[t0, "side"])})
    return pd.DataFrame(out).set_index("t0") if out else pd.DataFrame(
        columns=["y", "ret", "t1", "side"]
    )


def build_dataset(bars: pd.DataFrame, features: pd.DataFrame,
                  regimes: pd.DataFrame,
                  daily_positions: dict[str, pd.Series],
                  intraday_results: dict[str, tuple[pd.Series, pd.Series]],
                  barrier: BarrierConfig | None = None,
                  label_mode: str = "strategy",
                  daily_net: dict[str, pd.Series] | None = None) -> pd.DataFrame:
    """Dataset completo: X + y + t1 + metadatos (strategy, side).

    daily_positions: {nombre: posiciones objetivo SIN shift}.
    intraday_results: {nombre: (positions_daily, net_daily)} del motor.
    label_mode: 'strategy' (PnL propio a 10d, el de producción) o
    'barrier' (triple barrier clásico, mantenido para comparación).
    daily_net: {nombre: retornos netos diarios} — requerido en modo strategy.
    """
    atr_price = features["atr_14_pct"] * bars["close"]
    ctx = features[BASE_FEATURES].join(regimes[REGIME_FEATURES])
    rows = []

    for name, positions in daily_positions.items():
        events = daily_entry_events(positions)
        if events.empty:
            continue
        if label_mode == "strategy":
            labels = strategy_outcome_labels(events, daily_net[name])
        else:
            labels = triple_barrier_labels(bars, atr_price, events, barrier)
        if labels.empty:
            continue
        feats = ctx.reindex(labels.index)  # features al cierre de t0
        block = pd.concat([labels, feats], axis=1)
        block["strategy"] = name
        rows.append(block)

    for name, (positions_daily, net_daily) in intraday_results.items():
        events = intraday_day_events(positions_daily, net_daily)
        if events.empty:
            continue
        # decisión ANTES de que empiece el día → features de t0-1
        feats = ctx.shift(1).reindex(events.index)
        block = feats.copy()
        block["side"] = events["side"]
        block["ret"] = events["day_net"]
        block["y"] = (events["day_net"] > 0).astype(int)
        block["t1"] = events.index  # la etiqueta se resuelve el mismo día
        block["strategy"] = name
        rows.append(block)

    df = pd.concat(rows).sort_index()
    df = df.dropna(subset=REGIME_FEATURES)  # sin régimen (pre-2010) no hay fila
    df.index.name = "t0"
    return df


def to_feature_matrix(dataset: pd.DataFrame) -> pd.DataFrame:
    """X para XGBoost: features + side + one-hot de la estrategia.

    XGBoost tolera NaN en features (los enruta), así que no imputamos.
    """
    x = dataset[BASE_FEATURES + REGIME_FEATURES + ["side"]].copy()
    for name in sorted(dataset["strategy"].unique()):
        x[f"strat_{name}"] = (dataset["strategy"] == name).astype(int)
    return x
