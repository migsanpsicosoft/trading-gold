"""Paper broker interno: paper trading sin broker externo ni KYC.

Para un sistema que opera UNA vez al día al cierre, un broker demo
solo aporta teatro. Este broker virtual hace lo mismo con más control:

  - Precios: el último cierre de XAU y EURUSD de NUESTRA base (que se
    alimenta sola de fuentes independientes — la evidencia sigue
    siendo virgen: la decisión se registra hoy, los precios de mañana
    llegan de fuera).
  - Fills: al cierre ± medio spread REAL (el spread_mean medido de
    Dukascopy del día; fallback conservador si falta).
  - Cuenta: cash en EUR + posición, persistidas en SQLite. El balance
    reportado es mark-to-market (cash + posición × mid, en EUR).

Misma interfaz que OandaBroker: el runner no distingue. Cuando llegue
la Fase 8 (dinero real) el broker externo será inevitable — y su KYC
también; hasta entonces, esto mide exactamente lo que hay que medir.
"""

import sqlite3

from gold_bot.config import settings
from gold_bot.data.db import connect
from gold_bot.execution.broker import BrokerState
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

FALLBACK_SPREAD = 0.45  # $/oz


class PaperBroker:
    """Broker virtual persistente (tabla paper_account)."""

    def _load_market(self, conn: sqlite3.Connection) -> tuple[float, float, float]:
        price = conn.execute(
            "SELECT close FROM bars WHERE symbol='XAU' ORDER BY date DESC LIMIT 1"
        ).fetchone()
        eur_usd = conn.execute(
            "SELECT close FROM bars WHERE symbol='EUR' ORDER BY date DESC LIMIT 1"
        ).fetchone()
        spread = conn.execute(
            "SELECT ask_close - bid_close FROM intraday_bars WHERE symbol='XAU' "
            "ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if price is None or eur_usd is None:
            raise RuntimeError("paper broker: sin precios de XAU/EUR en la base")
        return (float(price[0]), float(eur_usd[0]),
                float(spread[0]) if spread and spread[0] else FALLBACK_SPREAD)

    def _load_account(self, conn: sqlite3.Connection) -> tuple[float, float]:
        row = conn.execute(
            "SELECT cash_eur, held_units FROM paper_account WHERE id = 1"
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO paper_account (id, cash_eur, held_units) VALUES (1, ?, 0)",
                (settings.paper_capital_eur,),
            )
            conn.commit()
            log.info("paper_cuenta_creada", capital=settings.paper_capital_eur)
            return settings.paper_capital_eur, 0.0
        return float(row[0]), float(row[1])

    def state(self) -> BrokerState:
        conn = connect()
        try:
            mid, eur_usd, spread = self._load_market(conn)
            cash, held = self._load_account(conn)
        finally:
            conn.close()
        equity_eur = cash + held * mid / eur_usd  # mark-to-market
        return BrokerState(
            balance=round(equity_eur, 2),
            currency="EUR",
            held_units=held,
            bid=mid - spread / 2,
            ask=mid + spread / 2,
            eur_usd=eur_usd,
        )

    def market_order(self, units: int) -> dict:
        """Fill inmediato al cierre ± medio spread (en EUR)."""
        conn = connect()
        try:
            mid, eur_usd, spread = self._load_market(conn)
            cash, held = self._load_account(conn)
            fill = mid + spread / 2 if units > 0 else mid - spread / 2
            cash -= units * fill / eur_usd
            held += units
            conn.execute(
                "UPDATE paper_account SET cash_eur = ?, held_units = ? WHERE id = 1",
                (cash, held),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("paper_orden", units=units, fill=round(fill, 2))
        return {"paper": True, "units": units, "fill_price": round(fill, 4)}


def get_broker():
    """OANDA si hay credenciales; si no, el paper broker interno."""
    if settings.oanda_api_key and settings.oanda_account_id:
        from gold_bot.execution.broker import OandaBroker

        return OandaBroker.from_settings()
    log.info("broker_paper_interno")
    return PaperBroker()
