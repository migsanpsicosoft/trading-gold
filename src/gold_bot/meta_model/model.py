"""XGBoost meta-modelo: evaluación purgada y predicción walk-forward.

Dos modos, para dos preguntas distintas:

  - purged_cv_auc: ¿tiene skill el modelo? K-fold purgado con embargo
    sobre todo el dataset → AUC honesto.
  - walkforward_probs: ¿qué habría dicho el modelo cada día en
    producción? Re-fit periódico usando SOLO señales pasadas ya
    resueltas (t1 < inicio del segmento — la purga del walk-forward),
    prediciendo el periodo siguiente. Este es el camino de producción:
    con los datos auto-actualizados, cada re-fit absorbe lo nuevo y
    el modelo no se degrada por deriva del mercado.

Hiperparámetros conservadores y fijos (max_depth=3): el dataset tiene
~miles de filas; un árbol profundo memoriza ruido. No se tunean contra
el OOS (eso sería quemar el out-of-sample).
"""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

from gold_bot.config import settings
from gold_bot.meta_model.purged_kfold import PurgedKFold
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

MIN_TRAIN_SAMPLES = 500
# Simulación 2026-07-04 (grid ventana × frecuencia, labels v1 y v2): las
# 6 configuraciones dieron AUC walk-forward 0.50-0.52 — diferencias
# dentro del ruido. Se fija la opción más simple y robusta: reentreno
# trimestral con ventana expansiva. OJO: el modelo aún no tiene skill
# accionable (ver informe Fase 4); no usar como filtro duro.
DEFAULT_REFIT_FREQ = "QE"
DEFAULT_TRAIN_WINDOW: int | None = None


def make_model() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=settings.random_seed,
        n_jobs=4,
    )


def purged_cv_auc(x: pd.DataFrame, y: pd.Series, t1: pd.Series,
                  n_splits: int = 5, embargo_pct: float = 0.02) -> list[float]:
    """AUC por fold con purga y embargo."""
    cv = PurgedKFold(n_splits=n_splits, embargo_pct=embargo_pct)
    aucs = []
    for train_idx, test_idx in cv.split(x.index, t1):
        model = make_model()
        model.fit(x.iloc[train_idx], y.iloc[train_idx])
        proba = model.predict_proba(x.iloc[test_idx])[:, 1]
        aucs.append(float(roc_auc_score(y.iloc[test_idx], proba)))
    return aucs


def walkforward_probs(x: pd.DataFrame, y: pd.Series, t1: pd.Series,
                      refit_freq: str = DEFAULT_REFIT_FREQ,
                      train_window_days: int | None = DEFAULT_TRAIN_WINDOW,
                      ) -> pd.Series:
    """Probabilidad walk-forward de cada señal, como en producción.

    Para cada periodo (trimestre/año), entrena con las señales cuya
    etiqueta ya estaba RESUELTA antes de que empiece el periodo
    (t1 < inicio → purga implícita) y predice las señales del periodo.
    train_window_days: None = ventana expansiva; N = solo últimos N días.
    """
    t0 = x.index
    period_starts = pd.date_range(t0.min(), t0.max(), freq=refit_freq)
    probs = pd.Series(np.nan, index=t0)

    for i, start in enumerate(period_starts):
        is_last = i + 1 >= len(period_starts)
        end = t0.max() + pd.Timedelta(days=1) if is_last else period_starts[i + 1]
        test_mask = (t0 >= start) & (t0 < end)
        if not test_mask.any():
            continue
        train_mask = t1.to_numpy() < np.datetime64(start)  # etiqueta resuelta
        if train_window_days is not None:
            window_start = start - pd.Timedelta(days=train_window_days)
            train_mask &= t0.to_numpy() >= np.datetime64(window_start)
        if train_mask.sum() < MIN_TRAIN_SAMPLES:
            continue
        model = make_model()
        model.fit(x[train_mask], y[train_mask])
        probs[test_mask] = model.predict_proba(x[test_mask])[:, 1]

    return probs


def feature_importance(x: pd.DataFrame, y: pd.Series) -> list[dict]:
    """Importancia (gain) de un fit sobre todo el dataset.

    Solo para INSPECCIÓN de qué mira el modelo — nunca para evaluar
    skill (para eso está el CV purgado).
    """
    model = make_model()
    model.fit(x, y)
    imp = model.get_booster().get_score(importance_type="gain")
    total = sum(imp.values()) or 1.0
    ranked = sorted(imp.items(), key=lambda kv: kv[1], reverse=True)
    return [{"feature": k, "gain_pct": v / total} for k, v in ranked]
