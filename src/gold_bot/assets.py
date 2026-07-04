"""Registro de activos tradeables del sistema multi-activo.

Cada activo corre su propio "libro": estrategias universales + HMM de
régimen propio + gating + risk parity interno. Las capas globales
(pesos entre activos, vol targeting, freno) viven en risk.multi_asset.

fallback_spread: en unidades de precio del activo, usado donde no hay
spread intradía medido (se sustituye por el real de Dukascopy cuando
existe). Valores conservadores de broker retail.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetConfig:
    key: str                # símbolo interno (tabla bars / intraday_bars)
    name: str
    oanda_instrument: str   # para la ejecución (Fase 7 v2)
    fallback_spread: float  # unidades de precio
    full_book: bool = False  # True = usa TODAS las estrategias (solo oro)


TRADEABLE_ASSETS: dict[str, AssetConfig] = {
    "XAU": AssetConfig("XAU", "Oro", "XAU_USD", 0.45, full_book=True),
    "XAG": AssetConfig("XAG", "Plata", "XAG_USD", 0.025),
    "EUR": AssetConfig("EUR", "EUR/USD", "EUR_USD", 0.00012),
    "WTI": AssetConfig("WTI", "Petróleo WTI", "WTICO_USD", 0.035),
    "SPX": AssetConfig("SPX", "S&P 500", "SPX500_USD", 0.6),
    # Segunda oleada (2026-07-04): un representante por familia
    "JPY": AssetConfig("JPY", "USD/JPY", "USD_JPY", 0.018),
    "HG": AssetConfig("HG", "Cobre", "XCU_USD", 0.006),
    "NG": AssetConfig("NG", "Gas natural", "NATGAS_USD", 0.009),
    "USB": AssetConfig("USB", "T-Bond 30Y", "USB30Y_USD", 0.04),
}
