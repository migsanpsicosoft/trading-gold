"""Stress tests de la cartera final.

Tres ángulos:
  1. Episodios: los peores drawdowns históricos con duración y
     recuperación — cuánto duele y cuánto dura el dolor.
  2. Ventanas de crisis conocidas: cómo se comportó el sistema en los
     eventos que todo el mundo recuerda (solo reporting, no se
     optimiza nada contra ellas).
  3. Shock instantáneo: con la exposición de HOY, ¿qué pasa si el oro
     se mueve ±X% mañana? Aritmética simple exposición × movimiento.
"""

import numpy as np
import pandas as pd

CRISIS_WINDOWS = [
    ("COVID crash", "2020-02-15", "2020-04-15"),
    ("Invasión de Ucrania", "2022-02-01", "2022-04-30"),
    ("Subidas de tipos 2022", "2022-08-01", "2022-11-30"),
    ("Crisis bancaria (SVB)", "2023-03-01", "2023-04-15"),
]


def drawdown_episodes(returns: pd.Series, top: int = 5) -> list[dict]:
    """Los `top` peores episodios pico → valle → recuperación."""
    equity = np.exp(returns.fillna(0).cumsum())
    peak = equity.cummax()
    dd = equity / peak - 1

    episodes = []
    in_dd = False
    start = trough_date = None
    trough = 0.0
    for date, value in dd.items():
        if not in_dd and value < 0:
            in_dd, start, trough, trough_date = True, date, value, date
        elif in_dd:
            if value < trough:
                trough, trough_date = value, date
            if value == 0:
                episodes.append({"start": start, "trough": trough_date,
                                 "end": date, "depth": trough})
                in_dd = False
    if in_dd:  # episodio aún abierto
        episodes.append({"start": start, "trough": trough_date,
                         "end": None, "depth": trough})

    episodes.sort(key=lambda e: e["depth"])
    out = []
    for e in episodes[:top]:
        days = (e["trough"] - e["start"]).days
        recovery = (e["end"] - e["trough"]).days if e["end"] is not None else None
        out.append({
            "start": e["start"].date().isoformat(),
            "depth": round(float(e["depth"]), 4),
            "days_to_trough": days,
            "days_to_recover": recovery,  # None = aún en curso
        })
    return out


def crisis_performance(returns: pd.Series) -> list[dict]:
    """Retorno y DD del sistema en cada ventana de crisis conocida."""
    out = []
    for name, start, end in CRISIS_WINDOWS:
        window = returns[(returns.index >= start) & (returns.index <= end)]
        if len(window) < 5:
            continue
        equity = np.exp(window.fillna(0).cumsum())
        out.append({
            "name": name,
            "period": f"{start} → {end}",
            "return": round(float(equity.iloc[-1] - 1), 4),
            "max_dd": round(float((equity / equity.cummax() - 1).min()), 4),
        })
    return out


def shock_table(net_exposure: float) -> list[dict]:
    """Impacto inmediato en cartera de un movimiento del oro mañana."""
    return [
        {"gold_move": move, "portfolio_impact": round(net_exposure * move, 4)}
        for move in (-0.10, -0.05, -0.02, 0.02, 0.05, 0.10)
    ]
