"""Triple barrier labeling (López de Prado, AFML cap. 3).

¿Cómo se etiqueta si una señal "funcionó"? Con las tres barreras con
las que se gestiona un trade real desde la entrada:

  - profit-taking: entrada + lado × pt_mult × ATR
  - stop-loss:     entrada − lado × sl_mult × ATR
  - tiempo:        max_days días de paciencia

La PRIMERA barrera tocada decide: profit → y=1; stop → y=0; tiempo →
y=1 si el retorno acumulado (ajustado por lado) es positivo. Se usa
high/low diario para detectar el toque (no solo el cierre).

Además de y, devolvemos t1 (fecha de resolución de la etiqueta):
imprescindible para la purga del K-fold — una muestra cuya etiqueta
se resuelve DENTRO del test no puede estar en el train.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BarrierConfig:
    pt_mult: float = 1.5   # barrera de beneficio en múltiplos de ATR
    sl_mult: float = 1.5   # barrera de stop en múltiplos de ATR
    max_days: int = 10     # barrera temporal


def triple_barrier_labels(bars: pd.DataFrame, atr: pd.Series,
                          events: pd.DataFrame,
                          config: BarrierConfig | None = None) -> pd.DataFrame:
    """Etiqueta cada evento (señal de entrada) con las tres barreras.

    bars: OHLC diario (high/low/close).
    atr: ATR en unidades de precio, alineado con bars.
    events: DataFrame con índice = fecha de señal (t0) y columna 'side'
            (+1 largo, -1 corto).

    Devuelve DataFrame indexado como events con: y (0/1), ret (retorno
    del trade ajustado por lado), t1 (fecha de resolución).
    """
    cfg = config or BarrierConfig()
    idx = bars.index
    high, low, close = bars["high"], bars["low"], bars["close"]

    out = []
    for t0, ev in events.iterrows():
        side = float(ev["side"])
        if t0 not in idx:
            continue
        pos0 = idx.get_loc(t0)
        entry = close.iloc[pos0]
        a = atr.iloc[pos0]
        if np.isnan(a) or entry <= 0:
            continue

        pt = entry + side * cfg.pt_mult * a
        sl = entry - side * cfg.sl_mult * a
        window = idx[pos0 + 1: pos0 + 1 + cfg.max_days]

        y, ret, t1 = None, None, None
        for t in window:
            hi, lo = high.loc[t], low.loc[t]
            hit_pt = hi >= pt if side > 0 else lo <= pt
            hit_sl = lo <= sl if side > 0 else hi >= sl
            if hit_pt and hit_sl:
                # ambas tocadas el mismo día: sin intradía no sabemos el
                # orden → conservador: cuenta como stop
                hit_pt = False
            if hit_sl:
                y, ret, t1 = 0, side * (sl / entry - 1), t
                break
            if hit_pt:
                y, ret, t1 = 1, side * (pt / entry - 1), t
                break
        if y is None:
            if len(window) == 0:
                continue  # señal en el último día: sin ventana, sin etiqueta
            t1 = window[-1]
            ret = side * (close.loc[t1] / entry - 1)
            y = int(ret > 0)

        out.append({"t0": t0, "y": y, "ret": float(ret), "t1": t1, "side": side})

    return pd.DataFrame(out).set_index("t0") if out else pd.DataFrame(
        columns=["y", "ret", "t1", "side"]
    )
