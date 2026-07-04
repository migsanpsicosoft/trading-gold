"""Endpoints del meta-modelo (Fase 4)."""

from functools import lru_cache

import numpy as np
from fastapi import APIRouter
from sklearn.metrics import roc_auc_score

from gold_bot.api.data import _data_version
from gold_bot.data.db import connect
from gold_bot.meta_model.model import (
    DEFAULT_REFIT_FREQ,
    DEFAULT_TRAIN_WINDOW,
    feature_importance,
    purged_cv_auc,
)
from gold_bot.meta_model.pipeline import TAKE_THRESHOLD, run_meta_pipeline

router = APIRouter(prefix="/api/meta")


@lru_cache(maxsize=1)
def _meta_for_version(version: tuple) -> dict:
    result = run_meta_pipeline(refit_freq=DEFAULT_REFIT_FREQ,
                               train_window_days=DEFAULT_TRAIN_WINDOW)
    dataset, x, probs = result["dataset"], result["x"], result["probs"]

    valid = probs.dropna()
    wf_auc = float(roc_auc_score(dataset["y"][probs.notna()], valid)) \
        if len(valid) > 100 else None
    cv_aucs = purged_cv_auc(x, dataset["y"], dataset["t1"])
    importance = feature_importance(x, dataset["y"])[:15]

    recent = dataset.tail(40).copy()
    recent["prob"] = probs.tail(40)
    decisions = [
        {
            "date": t0.date().isoformat(),
            "strategy": row["strategy"],
            "side": int(row["side"]),
            "prob": None if np.isnan(row["prob"]) else round(float(row["prob"]), 3),
            "taken": bool(np.isnan(row["prob"]) or row["prob"] >= TAKE_THRESHOLD),
            "outcome": int(row["y"]),
        }
        for t0, row in recent.iterrows()
    ]

    return {
        "config": {
            "refit_freq": DEFAULT_REFIT_FREQ,
            "train_window_days": DEFAULT_TRAIN_WINDOW,
            "threshold": TAKE_THRESHOLD,
        },
        "n_samples": int(len(dataset)),
        "base_rate": round(float(dataset["y"].mean()), 3),
        "cv_auc": {"folds": [round(a, 3) for a in cv_aucs],
                   "mean": round(float(np.mean(cv_aucs)), 3)},
        "wf_auc": None if wf_auc is None else round(wf_auc, 3),
        "signals_taken_pct": round(float((valid >= TAKE_THRESHOLD).mean()), 3),
        "importance": [
            {"feature": i["feature"], "gain_pct": round(i["gain_pct"], 4)}
            for i in importance
        ],
        "uplift": result["uplift"],
        "recent_decisions": decisions,
    }


@router.get("")
def meta() -> dict:
    """Estado del meta-modelo: skill, importancia, uplift y decisiones."""
    conn = connect()
    try:
        version = _data_version(conn)
    finally:
        conn.close()
    return _meta_for_version(version)
