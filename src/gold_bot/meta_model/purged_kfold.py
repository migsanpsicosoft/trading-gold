"""Purged K-Fold con embargo (López de Prado, AFML cap. 7).

El K-fold clásico baraja aleatoriamente. En finanzas eso filtra
información: la etiqueta de una muestra del 3 de enero se resuelve el
13 (su t1); si el test empieza el 10, esa muestra de train "vio" parte
del test.

  - PURGA: se eliminan del train las muestras cuya ventana [t0, t1]
    se solapa con el rango temporal del test.
  - EMBARGO: colchón adicional tras el test (pct del dataset) que
    también se excluye del train — protege de correlación serial que
    la purga exacta no captura.
"""

from collections.abc import Iterator

import numpy as np
import pandas as pd


class PurgedKFold:
    """K-fold temporal con purga y embargo.

    Los folds de test son bloques CONTIGUOS en el tiempo (sin barajar).
    Requiere t1: la fecha en que se resuelve la etiqueta de cada muestra.
    """

    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.02):
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, t0: pd.DatetimeIndex,
              t1: pd.Series) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Genera (train_idx, test_idx) posicionales.

        t0: fechas de señal (ordenadas ascendente).
        t1: fecha de resolución de cada etiqueta (misma longitud).
        """
        n = len(t0)
        if not t0.is_monotonic_increasing:
            raise ValueError("t0 debe estar ordenado ascendente")
        embargo = int(n * self.embargo_pct)
        folds = np.array_split(np.arange(n), self.n_splits)

        for test_idx in folds:
            test_start = t0[test_idx[0]]
            test_end = t1.iloc[test_idx].max()

            train_mask = np.ones(n, dtype=bool)
            train_mask[test_idx] = False
            # PURGA: fuera todo train cuya ventana [t0, t1] toque el test
            overlap = (t0 <= test_end) & (t1.to_numpy() >= np.datetime64(test_start))
            train_mask &= ~overlap
            # EMBARGO: colchón posicional tras el final del test
            last = test_idx[-1]
            train_mask[last + 1: last + 1 + embargo] = False

            yield np.where(train_mask)[0], test_idx
