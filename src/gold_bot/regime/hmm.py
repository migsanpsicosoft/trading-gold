"""Detector de régimen de mercado: HMM gaussiano walk-forward.

Un Hidden Markov Model asume N estados ocultos (regímenes) que no
observamos; solo vemos sus síntomas (retorno y volatilidad diarios).
EM aprende sin etiquetas la distribución de síntomas de cada estado y
la matriz de transición (los regímenes son "pegajosos": estar en
crisis hoy hace probable seguir mañana).

LAS DOS PROTECCIONES ANTI-LEAKAGE DE ESTE MÓDULO:

  1. WALK-FORWARD: el modelo se re-entrena cada 1 de enero usando SOLO
     datos anteriores; sus predicciones valen para el año siguiente.
     Nada de fit(todo) y pintar el pasado.
  2. PROBABILIDADES FILTRADAS, no suavizadas: P(estado_t | datos hasta
     t) vía el forward algorithm. Las suavizadas de predict_proba()
     usan la secuencia COMPLETA — saber cómo acabó marzo 2020 para
     clasificar marzo 2020.

Los estados del HMM son anónimos y cada re-fit puede barajarlos; se
reordenan SIEMPRE por volatilidad media: 0 = calma ... N-1 = turbulencia.
"""

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.stats import multivariate_normal

from gold_bot.config import settings
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

N_STATES = 3
FIRST_FIT_YEAR = 2010   # primer fit con 2005-2009; antes no hay historia mínima
MIN_TRAIN_DAYS = 500

REGIME_LABELS = ["calma", "transición", "turbulencia"]


def build_regime_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """Síntomas observables del régimen: retorno diario y log-volatilidad.

    log(vol) porque la volatilidad es multiplicativa (pasar de 10%→20%
    es tan grande como 20%→40%); en log, la gaussiana del HMM encaja.
    """
    x = pd.DataFrame(
        {"ret_1d": features["ret_1d"], "log_vol": np.log(features["vol_20d"])}
    ).dropna()
    return x[~np.isinf(x["log_vol"])]


def _fit(x_train: np.ndarray) -> GaussianHMM:
    model = GaussianHMM(
        n_components=N_STATES,
        covariance_type="full",
        n_iter=200,
        random_state=settings.random_seed,
    )
    model.fit(x_train)
    return model


def _state_order(model: GaussianHMM) -> np.ndarray:
    """Permutación que ordena los estados por log-vol media ascendente."""
    return np.argsort(model.means_[:, 1])


def filtered_probs(model: GaussianHMM, x: np.ndarray) -> np.ndarray:
    """Forward algorithm normalizado: P(estado_t | x_1..t).

    Solo mira el pasado: la recursión alpha avanza en el tiempo sin
    tocar observaciones futuras (a diferencia de predict_proba, que
    suaviza con la secuencia completa).
    """
    n, k = len(x), model.n_components
    log_b = np.column_stack([
        multivariate_normal.logpdf(x, mean=model.means_[j], cov=model.covars_[j])
        for j in range(k)
    ])
    alpha = np.zeros((n, k))
    a = model.startprob_ * np.exp(log_b[0] - log_b[0].max())
    alpha[0] = a / a.sum()
    for t in range(1, n):
        b = np.exp(log_b[t] - log_b[t].max())
        a = (alpha[t - 1] @ model.transmat_) * b
        alpha[t] = a / a.sum()
    return alpha


def walkforward_regimes(features: pd.DataFrame,
                        first_fit_year: int = FIRST_FIT_YEAR) -> pd.DataFrame:
    """Regímenes walk-forward: re-fit cada 1 de enero, filtrado el año siguiente.

    Devuelve DataFrame con prob_0..prob_{N-1} (ordenadas por volatilidad)
    y regime = argmax, solo para fechas posteriores al primer fit.
    """
    xdf = build_regime_matrix(features)
    segments = []
    for year in range(first_fit_year, xdf.index[-1].year + 1):
        train_end = pd.Timestamp(f"{year}-01-01")
        seg_end = pd.Timestamp(f"{year + 1}-01-01")
        train = xdf[xdf.index < train_end]
        if len(train) < MIN_TRAIN_DAYS:
            continue
        # estandarización SOLO con estadísticas del train (anti-leakage)
        mu, sigma = train.mean(), train.std()
        model = _fit(((train - mu) / sigma).to_numpy())
        order = _state_order(model)

        # forward sobre todo el pasado + el segmento (el modelo es del
        # pasado; la recursión solo usa datos hasta cada t)
        upto = xdf[xdf.index < seg_end]
        probs = filtered_probs(model, ((upto - mu) / sigma).to_numpy())[:, order]
        mask = upto.index >= train_end
        segments.append(pd.DataFrame(
            probs[mask],
            index=upto.index[mask],
            columns=[f"prob_{i}" for i in range(N_STATES)],
        ))
        log.info("regimen_fit", anno=year, dias_train=len(train))

    out = pd.concat(segments)
    out["regime"] = out.to_numpy().argmax(axis=1)
    return out


def regime_stats(features: pd.DataFrame, regimes: pd.DataFrame) -> list[dict]:
    """Caracterización de cada régimen: retorno y vol anualizados, % días."""
    ret = features["ret_1d"].reindex(regimes.index)
    stats = []
    for k in range(N_STATES):
        r = ret[regimes["regime"] == k]
        stats.append({
            "id": k,
            "label": REGIME_LABELS[k],
            "ann_return": float(r.mean() * 252) if len(r) else None,
            "ann_vol": float(r.std() * np.sqrt(252)) if len(r) > 1 else None,
            "days_pct": float(len(r) / len(regimes)),
        })
    return stats
