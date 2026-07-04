"""Tests del meta-modelo: triple barrier, purged K-fold y walk-forward."""

import numpy as np
import pandas as pd

from gold_bot.meta_model.labeling import BarrierConfig, triple_barrier_labels
from gold_bot.meta_model.model import walkforward_probs
from gold_bot.meta_model.purged_kfold import PurgedKFold


def make_bars(closes, highs=None, lows=None, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({
        "open": c,
        "high": pd.Series(highs, index=idx, dtype=float) if highs else c,
        "low": pd.Series(lows, index=idx, dtype=float) if lows else c,
        "close": c,
        "volume": 1.0,
    })


CFG = BarrierConfig(pt_mult=2.0, sl_mult=1.0, max_days=5)


def test_barrier_profit_hit_first():
    # entrada 100, ATR 1 → pt 102 / sl 99; el día 2 el high toca 102
    bars = make_bars([100, 101, 103, 103, 103, 103, 103],
                     highs=[100, 101.5, 103.5, 103, 103, 103, 103],
                     lows=[100, 100.5, 102, 103, 103, 103, 103])
    atr = pd.Series(1.0, index=bars.index)
    events = pd.DataFrame({"side": [1.0]}, index=[bars.index[0]])
    lab = triple_barrier_labels(bars, atr, events, CFG)
    assert lab["y"].iloc[0] == 1
    assert lab["t1"].iloc[0] == bars.index[2]
    assert lab["ret"].iloc[0] > 0


def test_barrier_stop_hit_first():
    bars = make_bars([100, 99.5, 98, 98, 98, 98, 98],
                     lows=[100, 98.9, 97.5, 98, 98, 98, 98])
    atr = pd.Series(1.0, index=bars.index)
    events = pd.DataFrame({"side": [1.0]}, index=[bars.index[0]])
    lab = triple_barrier_labels(bars, atr, events, CFG)
    assert lab["y"].iloc[0] == 0
    assert lab["t1"].iloc[0] == bars.index[1]  # sl 99 tocado el día 1


def test_barrier_time_expiry():
    # nunca toca barreras; a los 5 días cierra ligeramente arriba → y=1
    bars = make_bars([100, 100.2, 100.1, 100.3, 100.2, 100.4, 100.3, 100.2])
    atr = pd.Series(1.0, index=bars.index)
    events = pd.DataFrame({"side": [1.0]}, index=[bars.index[0]])
    lab = triple_barrier_labels(bars, atr, events, CFG)
    assert lab["y"].iloc[0] == 1
    assert lab["t1"].iloc[0] == bars.index[5]  # max_days=5


def test_barrier_short_side():
    # corto: pt abajo (98), sl arriba (101); cae → y=1
    bars = make_bars([100, 99, 97.5, 97, 97, 97, 97],
                     lows=[100, 98.5, 97, 97, 97, 97, 97])
    atr = pd.Series(1.0, index=bars.index)
    events = pd.DataFrame({"side": [-1.0]}, index=[bars.index[0]])
    lab = triple_barrier_labels(bars, atr, events, CFG)
    assert lab["y"].iloc[0] == 1
    assert lab["ret"].iloc[0] > 0


def test_barrier_ambiguous_day_counts_as_stop():
    # el día 1 toca AMBAS barreras → conservador: stop
    bars = make_bars([100, 100, 100, 100, 100, 100, 100],
                     highs=[100, 103, 100, 100, 100, 100, 100],
                     lows=[100, 98.5, 100, 100, 100, 100, 100])
    atr = pd.Series(1.0, index=bars.index)
    events = pd.DataFrame({"side": [1.0]}, index=[bars.index[0]])
    lab = triple_barrier_labels(bars, atr, events, CFG)
    assert lab["y"].iloc[0] == 0


# ------------------------------------------------------------ purged kfold
def test_purged_kfold_no_overlap():
    n = 200
    t0 = pd.bdate_range("2020-01-01", periods=n)
    t1 = pd.Series(t0 + pd.Timedelta(days=15), index=t0)  # etiquetas de ~10 días hábiles
    cv = PurgedKFold(n_splits=4, embargo_pct=0.02)
    folds = list(cv.split(t0, t1))
    assert len(folds) == 4
    for train_idx, test_idx in folds:
        test_start, test_end = t0[test_idx[0]], t1.iloc[test_idx].max()
        for i in train_idx:
            # ninguna muestra de train solapa su ventana con el test
            assert t1.iloc[i] < test_start or t0[i] > test_end
        assert len(set(train_idx) & set(test_idx)) == 0


def test_purged_kfold_embargo_applied():
    n = 100
    t0 = pd.bdate_range("2020-01-01", periods=n)
    t1 = pd.Series(t0, index=t0)  # etiquetas instantáneas: la purga no quita nada
    cv = PurgedKFold(n_splits=4, embargo_pct=0.10)
    train_idx, test_idx = next(iter(cv.split(t0, t1)))
    embargo_zone = set(range(test_idx[-1] + 1, test_idx[-1] + 1 + 10))
    assert embargo_zone.isdisjoint(train_idx)


# ------------------------------------------------------------ walk-forward
def test_walkforward_only_uses_resolved_past():
    """Con etiquetas que tardan 30 días en resolverse, las señales de los
    30 días previos a cada re-fit no pueden estar en su train. Lo
    comprobamos indirectamente: un 'leak detector' — la feature es el
    propio y futuro; si el modelo la viera del test, el AUC sería 1."""
    rng = np.random.default_rng(42)
    n = 1500
    t0 = pd.bdate_range("2018-01-01", periods=n)
    y = pd.Series(rng.integers(0, 2, n), index=t0)
    # feature = y con ruido → un modelo entrenado LEGALMENTE tiene skill,
    # pero solo sobre el train; y es i.i.d. → sin leakage el AUC del
    # walk-forward sobre y futuro debe rondar 0.5+algo, nunca ~1.0
    x = pd.DataFrame({
        "signal": y * 0.1 + rng.normal(0, 1, n),  # señal débil legal
        "noise": rng.normal(0, 1, n),
    }, index=t0)
    t1 = pd.Series(t0 + pd.Timedelta(days=30), index=t0)
    probs = walkforward_probs(x, y, t1, refit_freq="YE")
    valid = probs.dropna()
    assert len(valid) > 300
    from sklearn.metrics import roc_auc_score

    auc = roc_auc_score(y[valid.index], valid)
    assert 0.4 < auc < 0.75  # skill modesto legal; ~1.0 delataría leakage
