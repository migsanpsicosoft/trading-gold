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
from gold_bot.data.db import connect
from gold_bot.data.download import load_bars
from gold_bot.data.features import compute_asset_features, compute_features
from gold_bot.data.intraday import has_intraday_data, load_intraday_mid, load_intraday_ohlc
from gold_bot.regime.hmm import walkforward_regimes
from gold_bot.risk.gating import gate_matrix
from gold_bot.risk.portfolio import (
    drawdown_brake,
    inverse_vol_weights,
    vol_target_leverage,
)
from gold_bot.strategies import INTRADAY_STRATEGIES, STRATEGIES
from gold_bot.strategies.base import IntradayData, StrategyData
from gold_bot.strategies.breakout import Breakout
from gold_bot.strategies.mean_reversion import MeanReversion
from gold_bot.strategies.trend_following import TrendFollowing
from gold_bot.strategies.vol_breakout import VolBreakout
from gold_bot.utils.log import get_logger

log = get_logger(__name__)


def universal_daily_strategies() -> list:
    """Estrategias válidas en cualquier activo (instancias frescas)."""
    return [TrendFollowing(), Breakout(), MeanReversion()]


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
        bars15 = (load_intraday_ohlc(conn, key)
                  if has_intraday_data(conn, key) else pd.DataFrame())
    finally:
        conn.close()

    regimes = walkforward_regimes(features)
    data = StrategyData(bars=bars, features=features)
    spread = features.get("spread_mean")

    daily_strats = (list(STRATEGIES.values()) if config.full_book
                    else universal_daily_strategies())
    positions, nets = {}, {}
    for strat in daily_strats:
        pos = strat.generate_positions(data)
        positions[strat.name] = pos
        nets[strat.name] = run_backtest(
            bars, pos, spread_usd=spread,
            fallback_spread=config.fallback_spread,
        ).net_returns

    intraday_strats = (list(INTRADAY_STRATEGIES.values()) if config.full_book
                       else [VolBreakout()])
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
    # parity entre activos: reutiliza la misma función (los "gates" a
    # nivel activo son todo-1: la selección ya ocurrió dentro del libro)
    all_on = pd.DataFrame(1.0, index=streams.index, columns=streams.columns)
    asset_weights = inverse_vol_weights(
        {k: streams[k] for k in streams.columns}, all_on
    )
    combined = (streams * asset_weights).sum(axis=1)

    leverage = vol_target_leverage(combined, target_vol)
    levered = combined * leverage
    final, brake = drawdown_brake(levered)

    correlation = streams[streams.index >= OOS_START].corr()

    return {
        "books": books,
        "streams": streams,
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
