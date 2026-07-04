"""Estrategia 8: seasonality de sesiones (Asia / Londres / NY).

El día del oro tiene tres personalidades: Asia (demanda física),
Londres (fixes LBMA, flujo institucional) y NY (COMEX, macro USA).
La literatura documenta derivas sistemáticas por sesión que persisten
años (p. ej. debilidad alrededor del PM fix de Londres).

ANTI-LEAKAGE: no cableamos "Asia sube" tras mirar el histórico entero
(eso sería decidir 2016 con datos de 2026). La deriva de cada sesión
se estima con una ventana móvil de `lookback` días ANTERIORES, y solo
se opera una sesión si su t-stat reciente supera `t_threshold` — si el
patrón se evapora, la estrategia se apaga sola.

Sesiones (UTC): Asia 00-07h · Londres 07-13h · NY 13-21h · resto
(21-24h, mínima liquidez) siempre plano. Plana overnight como todas
las intradía.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from gold_bot.strategies.base import IntradayData, IntradayStrategy

SESSION_BINS = [0, 7, 13, 21, 24]
SESSION_LABELS = ["asia", "london", "ny", "late"]


@dataclass
class SessionSeasonality(IntradayStrategy):
    name: str = "session_seasonality"
    description: str = "Opera cada sesión solo si su deriva móvil 90d es significativa (|t|>2)"
    params: dict = field(default_factory=lambda: {"lookback": 90, "t_threshold": 2.0})

    def generate_positions(self, data: IntradayData) -> pd.Series:
        b = data.bars15
        lookback = self.params["lookback"]
        th = self.params["t_threshold"]

        ret = np.log(b["close"] / b["close"].shift(1))
        day = b.index.normalize()
        session = pd.Categorical.from_codes(
            np.digitize(b.index.hour, SESSION_BINS[1:-1]), categories=SESSION_LABELS
        )

        # retorno diario de cada sesión → matriz día × sesión
        frame = pd.DataFrame({"day": day, "session": session, "ret": ret.to_numpy()})
        sess_daily = (
            frame[frame["session"] != "late"]
            .groupby(["day", "session"], observed=True)["ret"]
            .sum()
            .unstack()
        )

        # deriva reciente por sesión, SOLO con días anteriores (shift(1))
        mean = sess_daily.rolling(lookback).mean().shift(1)
        std = sess_daily.rolling(lookback).std().shift(1)
        tstat = mean / (std / np.sqrt(lookback))

        signal = pd.DataFrame(
            np.where(tstat > th, 1.0, np.where(tstat < -th, -1.0, 0.0)),
            index=tstat.index, columns=tstat.columns,
        )
        signal[mean.isna()] = np.nan  # calentamiento de la ventana

        # mapear la señal (día, sesión) a cada barra
        keys = pd.MultiIndex.from_arrays([day, session])
        pos = signal.stack().reindex(keys).to_numpy()

        # sesión 'late' (no está en signal → NaN del reindex): plano, no warmup
        pos[np.asarray(session == "late")] = 0.0

        # plana en la última barra de cada día (contrato intradía)
        day_arr = day.to_numpy()
        is_last = np.r_[day_arr[:-1] != day_arr[1:], True]
        out = pd.Series(pos, index=b.index)
        out[is_last & out.notna()] = 0.0
        return out
