"""Contrato común de todas las estrategias.

Una estrategia es una función pura: datos → posiciones objetivo.

  - Posición objetivo ∈ [-1, +1]: fracción de la asignación de la
    estrategia (-1 corto total, 0 fuera, +1 largo total). El tamaño
    real en € lo decidirá el gestor de riesgo (Fase 5), no la
    estrategia.
  - La posición del día t se calcula con información hasta el CIERRE
    de t. El motor de backtest aplica shift(1): esa posición gana el
    retorno de t+1. Las estrategias NO hacen el shift ellas mismas
    (así es imposible olvidarlo o aplicarlo dos veces).
  - Sin estado ni I/O: mismos datos → mismas posiciones, siempre.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategyData:
    """Todo lo que una estrategia puede mirar.

    bars: OHLCV diario del oro (calendario de referencia).
    features: matriz de gold_bot.data.features (mismo índice).
    """

    bars: pd.DataFrame
    features: pd.DataFrame


@dataclass
class IntradayData:
    """Datos para estrategias intradía.

    bars15: OHLC en precio mid + spread + volumen, barras de 15 minutos
    (de load_intraday_ohlc). Timestamps UTC; el 'día' de agrupación es
    el día natural UTC.
    """

    bars15: pd.DataFrame


@dataclass
class Strategy(ABC):
    """Base de todas las estrategias. Subclases definen name,
    description, params (con defaults) y generate_positions()."""

    name: str = ""
    description: str = ""
    params: dict = field(default_factory=dict)

    @abstractmethod
    def generate_positions(self, data: StrategyData) -> pd.Series:
        """Posición objetivo diaria en [-1, +1], indexada como data.bars.

        Debe devolver valores para todo el índice (NaN solo durante el
        calentamiento de sus ventanas; el motor los trata como 0).
        """


@dataclass
class IntradayStrategy(Strategy):
    """Estrategia que opera DENTRO del día sobre barras de 15m.

    generate_positions recibe IntradayData y devuelve una posición por
    barra de 15m. Contrato adicional: posición 0 en la última barra de
    cada día (planas overnight) — el motor hace shift(1) por barra, así
    que una posición viva en la última barra capturaría el gap nocturno.
    """
