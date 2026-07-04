"""Features técnicas base sobre el calendario diario del oro.

REGLA ANTI-LEAKAGE (no negociable):
  - La feature del día t usa SOLO información disponible al cierre de t.
  - Ninguna normalización con estadísticas de toda la muestra: siempre
    ventanas móviles (rolling). Un z-score calculado con la media de
    2015-2026 le "cuenta el futuro" a 2016.
  - Los tests verifican que añadir datos futuros no cambia el pasado.

Los indicadores están implementados a mano (pandas puro) en vez de usar
pandas-ta: son pocas líneas, quedan testeados, y no dependemos de una
librería con historial de roturas con numpy.
"""

import numpy as np
import pandas as pd

TRADING_DAYS = 252  # días de trading/año, para anualizar volatilidades

# Descripciones para el dashboard
FEATURE_DESCRIPTIONS: dict[str, str] = {
    "ret_1d": "Retorno log de 1 día",
    "ret_5d": "Retorno log de 5 días",
    "ret_20d": "Retorno log de 20 días",
    "vol_20d": "Volatilidad realizada 20d (cierre a cierre, anualizada)",
    "atr_14_pct": "ATR(14) como % del precio — rango medio verdadero",
    "rsi_14": "RSI(14) con suavizado de Wilder",
    "sma_ratio_20": "Precio vs media móvil 20d (desviación %)",
    "sma_ratio_50": "Precio vs media móvil 50d (desviación %)",
    "sma_ratio_200": "Precio vs media móvil 200d (desviación %)",
    "xau_xag_ratio": "Ratio oro/plata",
    "xau_xag_z60": "Z-score móvil 60d del ratio oro/plata",
    "corr_dxy_20d": "Correlación móvil 20d con el índice dólar",
    "dxy_ret_20d": "Retorno log 20d del índice dólar",
    "us10y_chg_5d": "Cambio 5d del yield 10Y (puntos porcentuales)",
    "tip_ret_20d": "Retorno log 20d de TIP (proxy tipos reales, invertido al oro)",
    "rv_intraday": "Volatilidad realizada intradía (barras 15m, anualizada)",
    "spread_mean": "Spread bid/ask medio del día ($)",
}


# ------------------------------------------------------ indicadores base
def log_returns(close: pd.Series, periods: int = 1) -> pd.Series:
    """Retornos logarítmicos: aditivos en el tiempo y ~simétricos."""
    return np.log(close / close.shift(periods))


def realized_vol(ret_1d: pd.Series, window: int = 20) -> pd.Series:
    """Desviación típica móvil de retornos diarios, anualizada con √252."""
    return ret_1d.rolling(window).std() * np.sqrt(TRADING_DAYS)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average True Range: rango medio 'verdadero' (incluye gaps).

    True Range = max(high-low, |high-close_prev|, |low-close_prev|).
    Los dos últimos términos capturan huecos de apertura que high-low
    ignora. Base del position sizing por volatilidad (Fase 5).
    """
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"],
         (df["high"] - prev_close).abs(),
         (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, min_periods=window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """RSI con el suavizado original de Wilder (EWM con alpha=1/n).

    Muchas librerías usan medias simples y dan valores distintos al
    RSI 'canónico' de las plataformas de trading; usamos el de Wilder.
    """
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, min_periods=window).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def rolling_zscore(s: pd.Series, window: int = 60) -> pd.Series:
    """Z-score con media/std MÓVILES: cuántas desviaciones típicas se
    aleja el valor de su norma reciente. Nunca con stats de toda la
    muestra (leakage)."""
    return (s - s.rolling(window).mean()) / s.rolling(window).std()


# --------------------------------------------- features desde el intradía
def intraday_daily_stats(intraday: pd.DataFrame) -> pd.DataFrame:
    """Agrega las barras 15m a estadísticas diarias.

    - rv_intraday: √(Σ ret²) por día, anualizada. La volatilidad
      realizada intradía "ve" el movimiento dentro del día que la
      vol cierre-a-cierre se pierde (un día que sube 2% y baja 2%
      cierra plano pero fue muy volátil).
    - spread_mean: spread bid/ask medio del día en $.

    `intraday` viene de load_intraday_mid(): índice datetime, columnas
    mid y spread.
    """
    if intraday.empty:
        return pd.DataFrame(columns=["rv_intraday", "spread_mean"])
    ret = np.log(intraday["mid"] / intraday["mid"].shift(1))
    day = intraday.index.date
    rv = ret.groupby(day).apply(lambda r: np.sqrt((r**2).sum()) * np.sqrt(TRADING_DAYS))
    spread = intraday["spread"].groupby(day).mean()
    out = pd.DataFrame({"rv_intraday": rv, "spread_mean": spread})
    out.index = pd.to_datetime(out.index)
    return out


def compute_asset_features(bars: pd.DataFrame,
                           intraday: pd.DataFrame | None = None) -> pd.DataFrame:
    """Núcleo técnico genérico de un activo (expansión multi-activo).

    Es el subconjunto asset-agnóstico de compute_features: retornos,
    volatilidades, tendencia y microestructura del propio activo. Las
    features cross-asset (ratio con plata, DXY, tipos...) son del libro
    del oro y no entran aquí. Misma regla anti-leakage.
    """
    f = pd.DataFrame(index=bars.index)
    ret1 = log_returns(bars["close"])
    f["ret_1d"] = ret1
    f["ret_5d"] = log_returns(bars["close"], 5)
    f["ret_20d"] = log_returns(bars["close"], 20)
    f["vol_20d"] = realized_vol(ret1)
    f["atr_14_pct"] = atr(bars) / bars["close"]
    f["rsi_14"] = rsi(bars["close"])
    for w in (20, 50, 200):
        f[f"sma_ratio_{w}"] = bars["close"] / bars["close"].rolling(w).mean() - 1
    if intraday is not None and not intraday.empty:
        f = f.join(intraday_daily_stats(intraday))
    return f


# ------------------------------------------------------------ ensamblado
def _aligned_close(daily: dict[str, pd.DataFrame], symbol: str,
                   index: pd.Index) -> pd.Series | None:
    """Cierre de otro símbolo alineado al calendario del oro.

    reindex + ffill: si DXY no cotizó un día que el oro sí, usamos su
    último cierre CONOCIDO (pasado → sin leakage). Nunca bfill.
    """
    if symbol not in daily or daily[symbol].empty:
        return None
    return daily[symbol]["close"].reindex(index).ffill()


def compute_features(daily: dict[str, pd.DataFrame],
                     intraday_xau: pd.DataFrame | None = None) -> pd.DataFrame:
    """Matriz de features indexada por el calendario diario del oro."""
    xau = daily["XAU"]
    f = pd.DataFrame(index=xau.index)

    # --- retornos y volatilidad del oro
    ret1 = log_returns(xau["close"])
    f["ret_1d"] = ret1
    f["ret_5d"] = log_returns(xau["close"], 5)
    f["ret_20d"] = log_returns(xau["close"], 20)
    f["vol_20d"] = realized_vol(ret1)
    f["atr_14_pct"] = atr(xau) / xau["close"]
    f["rsi_14"] = rsi(xau["close"])
    for w in (20, 50, 200):
        f[f"sma_ratio_{w}"] = xau["close"] / xau["close"].rolling(w).mean() - 1

    # --- cross-asset
    xag = _aligned_close(daily, "XAG", xau.index)
    if xag is not None:
        ratio = xau["close"] / xag
        f["xau_xag_ratio"] = ratio
        f["xau_xag_z60"] = rolling_zscore(ratio, 60)

    dxy = _aligned_close(daily, "DXY", xau.index)
    if dxy is not None:
        dxy_ret = log_returns(dxy)
        f["corr_dxy_20d"] = ret1.rolling(20).corr(dxy_ret)
        f["dxy_ret_20d"] = log_returns(dxy, 20)

    us10y = _aligned_close(daily, "US10Y", xau.index)
    if us10y is not None:
        # ^TNX cotiza el yield multiplicado por 10 → /10 = puntos %
        f["us10y_chg_5d"] = us10y.diff(5) / 10

    tip = _aligned_close(daily, "TIP", xau.index)
    if tip is not None:
        f["tip_ret_20d"] = log_returns(tip, 20)

    # --- microestructura desde el intradía
    if intraday_xau is not None and not intraday_xau.empty:
        stats = intraday_daily_stats(intraday_xau)
        f = f.join(stats)

    return f
