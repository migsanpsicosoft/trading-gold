"""Cartera multi-activo: un libro por activo + capas globales.

Estructura (la matemática de Grinold: el Sharpe crece con la raíz del
número de apuestas INDEPENDIENTES):

  Por activo (libro):
    estrategias universales (trend, breakout, mean reversion, y vol
    breakout si hay intradía) → HMM de régimen propio → gating →
    risk parity interno → UN stream de retornos por activo.
    El oro usa además sus estrategias específicas (macro, stat arb,
    seasonality) — su libro completo de siempre.

  Global:
    risk parity ENTRE activos (1/vol de cada stream) → vol targeting
    → freno de drawdown. Las mismas capas validadas en Fase 5.
"""

from dataclasses import dataclass, field

import pandas as pd

from gold_bot.assets import TRADEABLE_ASSETS, AssetConfig
from gold_bot.backtest.intraday import run_intraday_backtest
from gold_bot.backtest.simple import OOS_START, compute_metrics, run_backtest
from gold_bot.data.cot import load_cot_daily
from gold_bot.data.db import connect
from gold_bot.data.download import load_bars
from gold_bot.data.features import compute_asset_features, compute_features
from gold_bot.data.intraday import has_intraday_data, load_intraday_mid, load_intraday_ohlc
from gold_bot.data.macro import load_macro_daily
from gold_bot.regime.hmm import walkforward_regimes
from gold_bot.risk.gating import gate_matrix
from gold_bot.risk.portfolio import (
    drawdown_brake,
    inverse_vol_weights,
    vol_target_leverage,
)
from gold_bot.strategies import INTRADAY_STRATEGIES, STRATEGIES
from gold_bot.strategies.base import IntradayData, StrategyData
from gold_bot.strategies.carry import CurveCarry, FxCarry
from gold_bot.strategies.cot_extreme import CotExtreme
from gold_bot.strategies.mean_reversion import MeanReversion
from gold_bot.strategies.monthly_seasonality import MonthlySeasonality
from gold_bot.strategies.risk_off_jpy import RiskOffJPY
from gold_bot.strategies.st_reversal import ShortTermReversal
from gold_bot.strategies.ts_momentum import TSMomentum
from gold_bot.strategies.vix_structure import VixStructure
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

COT_Z_WINDOW = 756  # ~3 años de días hábiles

# CRIBA por libro (2026-07-05): la MISMA regla aprobada para el oro en
# Fase 2 — fuera solo lo que no tiene nada que rescatar (Sharpe neto
# OOS < -0.15 medido en v3, sin valor de diversificación). Advertencia
# registrada: el OOS ya fue consultado en v1-v3; la validez de lo que
# quede la decide el paper trading hacia delante, no este backtest.
CRIBA_EXCLUDED: set[tuple[str, str]] = {
    ("XAG", "st_reversal"),      # -0.17
    ("WTI", "ts_momentum"),      # -0.75
    ("JPY", "mean_reversion"),   # -0.25
    ("JPY", "cot_extreme"),      # -0.21
    ("HG", "st_reversal"),       # -0.32
    ("HG", "cot_extreme"),       # -0.22
    ("NG", "cot_extreme"),       # -0.31
}

# Cartera sombra "top10": las 10 mejores células de v2/v3 medidas en
# OOS. ADVERTENCIA PRE-REGISTRADA: esto es selección descarada — el
# máximo de ~45 células evaluadas. Su backtest NO es creíble por
# construcción; existe SOLO como libro sombra para que la evidencia
# hacia delante la juzgue. Peso igual 1/10 por célula.
TOP_CELLS: list[tuple[str, str]] = [
    ("USB", "monthly_seasonality"),  # 0.73
    ("SPX", "cot_extreme"),          # 0.71
    ("SPX", "monthly_seasonality"),  # 0.58
    ("NG", "mean_reversion"),        # 0.53
    ("EUR", "mean_reversion"),       # 0.47
    ("NG", "st_reversal"),           # 0.47
    ("JPY", "fx_carry"),             # 0.45
    ("SPX", "vix_structure"),        # 0.45
    ("WTI", "cot_extreme"),          # 0.42
    ("JPY", "ts_momentum"),          # 0.40
]


def top_cells_exposures(books: dict) -> dict[str, float]:
    """Exposición por activo de la cartera top10 (1/10 por célula)."""
    exposures: dict[str, float] = {}
    for asset, strategy in TOP_CELLS:
        book = books.get(asset)
        if book is None or strategy not in book.positions:
            continue
        pos = book.positions[strategy].dropna()
        last = float(pos.iloc[-1]) if len(pos) else 0.0
        exposures[asset] = exposures.get(asset, 0.0) + last / len(TOP_CELLS)
    return exposures


def strategies_for_asset(key: str) -> tuple[list, list]:
    """Asignación de estrategias por activo — pre-registrada en
    docs/estrategias_v2.md y docs/estrategias_v3.md ANTES de evaluar.

    v2: TSMOM 12-1 + reversión 5d + Bollinger + estacionalidad mensual;
    RiskOffJPY en JPY. overnight_equity retirada (muerta por costes,
    riesgo pre-declarado en v2).
    v3 (datos nuevos): cot_extreme en todos; fx_carry en EUR y JPY;
    curve_carry en USB; vix_structure en SPX.
    """
    daily = [TSMomentum(), ShortTermReversal(), MeanReversion(),
             MonthlySeasonality(), CotExtreme()]
    if key == "JPY":
        daily += [RiskOffJPY(), FxCarry()]
    if key == "EUR":
        daily.append(FxCarry())
    if key == "USB":
        daily.append(CurveCarry())
    if key == "SPX":
        daily.append(VixStructure())
    daily = [s for s in daily if (key, s.name) not in CRIBA_EXCLUDED]
    return daily, []


def build_extra_features(key: str, bars: pd.DataFrame, conn) -> pd.DataFrame:
    """Features cross-fuente por activo (COT, carry, VIX). Todas con su
    disponibilidad temporal correcta (lags y ffill de solo-pasado)."""
    extra = pd.DataFrame(index=bars.index)

    cot = load_cot_daily(conn, key, bars.index)
    if cot.notna().any():
        mean = cot.rolling(COT_Z_WINDOW, min_periods=COT_Z_WINDOW // 3).mean()
        std = cot.rolling(COT_Z_WINDOW, min_periods=COT_Z_WINDOW // 3).std()
        extra["cot_z"] = (cot - mean) / std

    if key == "EUR":
        ecb = load_macro_daily(conn, "ECB", bars.index)
        us3m = load_macro_daily(conn, "US3M", bars.index)
        extra["carry_diff"] = ecb - us3m
    if key == "JPY":
        us3m = load_macro_daily(conn, "US3M", bars.index)
        jp = load_macro_daily(conn, "JPRATE", bars.index)
        extra["carry_diff"] = us3m - jp
        spx_close = load_bars(conn, "SPX")["close"]
        extra["spx_ret_60d"] = (spx_close / spx_close.shift(60) - 1) \
            .reindex(bars.index).ffill()
    if key == "USB":
        extra["curve_slope"] = load_macro_daily(conn, "T10Y2Y", bars.index)
    if key == "SPX":
        vix = load_bars(conn, "VIX")["close"].reindex(bars.index).ffill()
        vix3m = load_bars(conn, "VIX3M")["close"].reindex(bars.index).ffill()
        extra["vix_ratio"] = vix3m / vix - 1

    return extra


@dataclass
class AssetBook:
    config: AssetConfig
    bars: pd.DataFrame
    features: pd.DataFrame
    regimes: pd.DataFrame
    nets: dict[str, pd.Series]           # retornos netos por estrategia
    positions: dict[str, pd.Series]      # posiciones diarias por estrategia
    stream: pd.Series                    # retorno del libro (post gating+parity)
    net_exposure: pd.Series              # posición neta diaria del libro
    metrics: dict = field(default_factory=dict)


def build_asset_book(key: str) -> AssetBook:
    """Construye el libro completo de un activo (todo walk-forward)."""
    config = TRADEABLE_ASSETS[key]
    conn = connect()
    try:
        if config.full_book:
            # el oro conserva su libro original: features cross-asset y
            # sus 7 estrategias (incluidas las específicas)
            from gold_bot.data.download import SYMBOLS

            daily = {s: load_bars(conn, s) for s in SYMBOLS}
            bars = daily[key]
            features = compute_features(daily, load_intraday_mid(conn, key))
        else:
            bars = load_bars(conn, key)
            intraday_mid = (load_intraday_mid(conn, key)
                            if has_intraday_data(conn, key) else None)
            features = compute_asset_features(bars, intraday_mid)
            features = features.join(build_extra_features(key, bars, conn))
        bars15 = (load_intraday_ohlc(conn, key)
                  if has_intraday_data(conn, key) else pd.DataFrame())
    finally:
        conn.close()

    regimes = walkforward_regimes(features)
    data = StrategyData(bars=bars, features=features)
    spread = features.get("spread_mean")

    v2_daily, v2_intraday = strategies_for_asset(key)
    daily_strats = (list(STRATEGIES.values()) if config.full_book
                    else v2_daily)
    positions, nets = {}, {}
    for strat in daily_strats:
        pos = strat.generate_positions(data)
        positions[strat.name] = pos
        nets[strat.name] = run_backtest(
            bars, pos, spread_usd=spread,
            fallback_spread=config.fallback_spread,
        ).net_returns

    intraday_strats = (list(INTRADAY_STRATEGIES.values()) if config.full_book
                       else v2_intraday)
    intraday_nets = {}
    if not bars15.empty:
        for strat in intraday_strats:
            pos15 = strat.generate_positions(IntradayData(bars15))
            intraday_nets[strat.name] = run_intraday_backtest(bars15, pos15).net_returns
    nets.update(intraday_nets)

    # gating + risk parity DENTRO del libro (idéntico a Fase 5)
    gates = gate_matrix(nets, regimes["regime"])
    weights = inverse_vol_weights(nets, gates)

    idx = regimes.index
    combined_pos = pd.Series(0.0, index=bars.index)
    for name, pos in positions.items():
        w = weights[name].reindex(pos.index).fillna(0.0)
        combined_pos = combined_pos.add(pos.fillna(0.0) * w, fill_value=0.0)
    stream = run_backtest(
        bars, combined_pos, spread_usd=spread,
        fallback_spread=config.fallback_spread,
    ).net_returns.reindex(idx).fillna(0.0)
    for name, net in intraday_nets.items():
        w = weights[name].shift(1)
        stream = stream.add((net.reindex(idx) * w.reindex(idx)).fillna(0.0),
                            fill_value=0.0)

    book = AssetBook(
        config=config, bars=bars, features=features, regimes=regimes,
        nets=nets, positions=positions, stream=stream,
        net_exposure=combined_pos.reindex(idx).fillna(0.0),
        metrics={
            "oos": compute_metrics(stream[stream.index >= OOS_START]),
            "per_strategy_oos": {
                name: compute_metrics(net[net.index >= OOS_START])["sharpe"]
                for name, net in nets.items()
            },
        },
    )
    log.info("libro_construido", activo=key,
             oos_sharpe=book.metrics["oos"]["sharpe"])
    return book


def build_multi_portfolio(keys: list[str] | None = None,
                          target_vol: float = 0.10) -> dict:
    """Cartera global: libros por activo + parity entre activos +
    vol targeting + freno (config B)."""
    keys = keys or list(TRADEABLE_ASSETS)
    books = {k: build_asset_book(k) for k in keys}

    streams = pd.DataFrame({k: b.stream for k, b in books.items()})
    # GATE POR LIBRO (walk-forward): un libro solo pesa si su Sharpe
    # móvil de 250 días es positivo — la misma medicina del gating de
    # estrategias, un nivel más arriba. Un activo cuya receta no
    # funciona se apaga solo, sin cherry-picking sobre el OOS.
    # (conditional_gate con régimen constante = gate incondicional.)
    from gold_bot.risk.gating import conditional_gate

    neutral = pd.Series(0, index=streams.index)
    book_gates = pd.DataFrame(
        {k: conditional_gate(streams[k], neutral) for k in streams.columns}
    )
    asset_weights = inverse_vol_weights(
        {k: streams[k] for k in streams.columns}, book_gates
    )
    combined = (streams * asset_weights).sum(axis=1)

    leverage = vol_target_leverage(combined, target_vol)
    levered = combined * leverage
    final, brake = drawdown_brake(levered)

    correlation = streams[streams.index >= OOS_START].corr()

    return {
        "books": books,
        "streams": streams,
        "book_gates": book_gates,
        "asset_weights": asset_weights,
        "leverage": leverage,
        "brake": brake,
        "final_returns": final,
        "correlation": correlation,
        "metrics": {
            "per_asset_oos": {k: b.metrics["oos"] for k, b in books.items()},
            "combined_oos": compute_metrics(final[final.index >= OOS_START]),
            "combined_full": compute_metrics(final),
        },
    }
