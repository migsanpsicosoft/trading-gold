"""Simulación de cuenta: dry-run histórico del ejecutor.

Replica cómo habría operado el sistema con una cuenta real en euros:
órdenes discretas en onzas, balance día a día, costes por orden y
conversión EUR/USD diaria. Las señales son las del sistema walk-forward
(libres de leakage por construcción).

Lo que el backtest continuo esconde y esto revela:
  - DISCRETIZACIÓN: si el broker opera en pasos de 1 oz (~3.700€),
    una posición objetivo de 0.4 oz se redondea — con cuentas
    pequeñas el redondeo distorsiona mucho.
  - DIVISA: la cuenta es EUR pero el oro cotiza en USD; el PnL se
    convierte al EURUSD del día.

Aproximación documentada: las estrategias intradía no se simulan
orden a orden (sería otro simulador); su contribución entra como
ajuste diario de PnL proporcional a la equity. Su peso en la cartera
es minoritario.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

SLIPPAGE_BPS = 1.0


@dataclass
class AccountSim:
    ledger: pd.DataFrame   # una fila por día de trading
    summary: dict


def simulate_account(bars: pd.DataFrame, spread_usd: pd.Series,
                     net_exposure: pd.Series, intraday_contrib: pd.Series,
                     brake: pd.Series, eurusd: pd.Series,
                     start: str, end: str, capital_eur: float = 5000.0,
                     step_oz: float | None = None) -> AccountSim:
    """Simula la cuenta entre start y end.

    net_exposure: fracción de la equity en XAU decidida AL CIERRE de
    cada día (ya incluye gates, pesos, apalancamiento y freno).
    step_oz: granularidad mínima de orden del broker (None = fraccional).
    eurusd: USD por EUR, diario.
    """
    close = bars["close"]
    days = close.index[(close.index >= start) & (close.index <= end)]
    spread = spread_usd.reindex(close.index).ffill().fillna(0.45)
    fx = eurusd.reindex(close.index).ffill()
    exposure = net_exposure.reindex(close.index).fillna(0.0)
    intra = intraday_contrib.reindex(close.index).fillna(0.0)
    brake_m = brake.reindex(close.index).fillna(1.0)

    equity = capital_eur
    held_oz = 0.0
    prev_price = None
    rows = []

    for t in days:
        price, fx_t = float(close.loc[t]), float(fx.loc[t])
        # 1) PnL del gap+día por la posición que traíamos de ayer
        pnl_daily_eur = (held_oz * (price - prev_price) / fx_t
                         if prev_price is not None else 0.0)
        # 2) contribución intradía del día (agregada, ver docstring)
        pnl_intra_eur = equity * float(intra.loc[t]) * float(brake_m.loc[t])
        equity += pnl_daily_eur + pnl_intra_eur

        # 3) al cierre: nueva posición objetivo y orden
        target_usd = float(exposure.loc[t]) * equity * fx_t
        target_oz = target_usd / price
        if step_oz:
            target_oz = round(target_oz / step_oz) * step_oz
        order_oz = target_oz - held_oz
        cost_eur = (abs(order_oz)
                    * (float(spread.loc[t]) / 2 + price * SLIPPAGE_BPS / 10_000)
                    / fx_t)
        equity -= cost_eur
        held_oz = target_oz

        rows.append({"date": t, "price_usd": price, "eurusd": fx_t,
                     "target_oz": round(target_oz, 4),
                     "order_oz": round(order_oz, 4),
                     "cost_eur": round(cost_eur, 2),
                     "pnl_daily_eur": round(pnl_daily_eur, 2),
                     "pnl_intra_eur": round(pnl_intra_eur, 2),
                     "equity_eur": round(equity, 2)})
        prev_price = price

    ledger = pd.DataFrame(rows).set_index("date")
    eq = ledger["equity_eur"]
    dd = eq / eq.cummax() - 1
    n_orders = int((ledger["order_oz"].abs() > 1e-9).sum())
    summary = {
        "capital_inicial_eur": capital_eur,
        "capital_final_eur": round(float(eq.iloc[-1]), 2),
        "retorno_pct": round(float(eq.iloc[-1] / capital_eur - 1), 4),
        "max_dd_pct": round(float(dd.min()), 4),
        "n_ordenes": n_orders,
        "costes_totales_eur": round(float(ledger["cost_eur"].sum()), 2),
        "dias": len(ledger),
        "step_oz": step_oz,
    }
    return AccountSim(ledger=ledger, summary=summary)


def theoretical_equity(final_returns: pd.Series, start: str, end: str,
                       capital_eur: float = 5000.0) -> float:
    """Referencia: el backtest continuo (sin discretizar, sin FX)."""
    window = final_returns[(final_returns.index >= start)
                           & (final_returns.index <= end)]
    return round(float(capital_eur * np.exp(window.sum())), 2)
