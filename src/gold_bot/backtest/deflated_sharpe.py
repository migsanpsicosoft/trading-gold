"""Deflated Sharpe Ratio (Bailey & López de Prado, 2014).

El problema: si pruebas N configuraciones, la mejor tendrá un Sharpe
alto por pura selección — el "max de N monedas al aire". El DSR
responde: ¿qué probabilidad hay de que el Sharpe observado sea skill
real, dado cuántos intentos hiciste?

Dos piezas:
  - PSR (Probabilistic Sharpe Ratio): P(SR verdadero > SR*), con
    corrección por skew y curtosis de los retornos (un Sharpe de
    vender volatilidad tiene cola gorda y se penaliza).
  - SR0: el Sharpe que ESPERARÍAS del mejor de N intentos sin skill
    (fórmula del máximo esperado de N normales). DSR = PSR(SR0).

Los intentos del proyecto se cuentan honestamente en N_TRIALS y
TRIAL_SHARPES_ANNUAL (registrados según se hicieron, no reconstruidos).
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

TRADING_DAYS = 252
EULER_GAMMA = 0.5772156649

# Registro honesto de intentos del proyecto (2026-07-04):
#   8 estrategias construidas + 12 configuraciones del meta-modelo
#   (2 labels × 6 grids) + 3 configs de riesgo + 1 gating = 24
N_TRIALS = 24

# Sharpe anual OOS de los intentos medidos a nivel cartera/estrategia —
# su dispersión estima la varianza entre intentos que exige la fórmula
TRIAL_SHARPES_ANNUAL = [
    0.40, 0.28, -0.04, -0.15, 0.19, -0.14, -1.54, -0.14,  # 8 estrategias
    0.29, 0.26, 0.62, 0.70, 0.74, 0.76, 0.77, 0.80, 0.21,  # ensembles/configs
]


def probabilistic_sharpe(returns: pd.Series, sr_benchmark_daily: float) -> float:
    """PSR: P(SR verdadero > benchmark), con skew y curtosis."""
    r = returns.dropna()
    t = len(r)
    if t < 60 or r.std() == 0:
        return float("nan")
    sr = float(r.mean() / r.std())  # Sharpe por-periodo (diario)
    skew = float(r.skew())
    kurt = float(r.kurtosis()) + 3  # pandas da exceso; la fórmula usa curtosis plena
    denom = np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr**2)
    z = (sr - sr_benchmark_daily) * np.sqrt(t - 1) / denom
    return float(norm.cdf(z))


def expected_max_sharpe_daily(n_trials: int = N_TRIALS,
                              trial_sharpes_annual: list[float] | None = None) -> float:
    """SR0: el Sharpe diario esperado del MEJOR de n intentos sin skill."""
    trials = trial_sharpes_annual or TRIAL_SHARPES_ANNUAL
    trial_std_daily = float(np.std(trials, ddof=1)) / np.sqrt(TRADING_DAYS)
    return trial_std_daily * (
        (1 - EULER_GAMMA) * norm.ppf(1 - 1 / n_trials)
        + EULER_GAMMA * norm.ppf(1 - 1 / (n_trials * np.e))
    )


def deflated_sharpe(returns: pd.Series, n_trials: int = N_TRIALS) -> dict:
    """DSR completo: PSR contra el máximo esperado de n intentos.

    DSR > 0.95 = el Sharpe sobrevive a la corrección por multiple
    testing con 95% de confianza. DSR ~0.5 = indistinguible de suerte.
    """
    sr0 = expected_max_sharpe_daily(n_trials)
    dsr = probabilistic_sharpe(returns, sr0)
    r = returns.dropna()
    return {
        "dsr": round(dsr, 4),
        "sharpe_annual": round(float(r.mean() / r.std() * np.sqrt(TRADING_DAYS)), 3),
        "sr0_annual_equiv": round(float(sr0 * np.sqrt(TRADING_DAYS)), 3),
        "n_trials": n_trials,
        "skew": round(float(r.skew()), 3),
        "kurtosis": round(float(r.kurtosis()) + 3, 3),
        "days": len(r),
    }
