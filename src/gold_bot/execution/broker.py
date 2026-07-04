"""Conector OANDA v20 (cuenta practice).

Interfaz mínima que necesita el runner diario: estado de la cuenta
(balance, posición abierta, precios) y orden a mercado. El instrumento
es XAU_USD, que OANDA opera en unidades de 1 onza troy.

Toda la red vive aquí; el resto del módulo execution es lógica pura
testeable. La API key viene de .env (settings), nunca del código.
"""

from dataclasses import dataclass

import requests

from gold_bot.config import settings
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

INSTRUMENT = "XAU_USD"
TIMEOUT = 30


@dataclass
class BrokerState:
    balance: float          # en la divisa de la cuenta
    currency: str           # "EUR", "USD"...
    held_units: float       # onzas abiertas (negativo = corto)
    bid: float
    ask: float
    eur_usd: float | None   # USD por EUR (None si la cuenta es USD)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class OandaBroker:
    def __init__(self, api_key: str, account_id: str, practice: bool = True):
        if not api_key or not account_id:
            raise RuntimeError(
                "Faltan credenciales OANDA: define OANDA_API_KEY y "
                "OANDA_ACCOUNT_ID en el .env"
            )
        host = ("https://api-fxpractice.oanda.com" if practice
                else "https://api-fxtrade.oanda.com")
        self._base = f"{host}/v3/accounts/{account_id}"
        self._headers = {"Authorization": f"Bearer {api_key}"}

    @classmethod
    def from_settings(cls) -> "OandaBroker":
        return cls(settings.oanda_api_key, settings.oanda_account_id,
                   settings.oanda_practice)

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = requests.get(f"{self._base}{path}", headers=self._headers,
                         params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def state(self) -> BrokerState:
        summary = self._get("/summary")["account"]
        currency = summary["currency"]

        instruments = INSTRUMENT + (",EUR_USD" if currency == "EUR" else "")
        prices = self._get("/pricing", params={"instruments": instruments})["prices"]
        by_instrument = {p["instrument"]: p for p in prices}
        xau = by_instrument[INSTRUMENT]
        eur_usd = None
        if currency == "EUR":
            p = by_instrument["EUR_USD"]
            eur_usd = (float(p["bids"][0]["price"]) + float(p["asks"][0]["price"])) / 2

        try:
            pos = self._get(f"/positions/{INSTRUMENT}")["position"]
            held = float(pos["long"]["units"]) + float(pos["short"]["units"])
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                held = 0.0  # sin posición abierta
            else:
                raise

        return BrokerState(
            balance=float(summary["balance"]),
            currency=currency,
            held_units=held,
            bid=float(xau["bids"][0]["price"]),
            ask=float(xau["asks"][0]["price"]),
            eur_usd=eur_usd,
        )

    def market_order(self, units: int) -> dict:
        """Orden a mercado de `units` onzas (negativo = vender/corto)."""
        r = requests.post(
            f"{self._base}/orders",
            headers=self._headers,
            json={"order": {"type": "MARKET", "instrument": INSTRUMENT,
                            "units": str(int(units)),
                            "timeInForce": "FOK",
                            "positionFill": "DEFAULT"}},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        result = r.json()
        log.info("orden_enviada", units=units,
                 fill=result.get("orderFillTransaction", {}).get("price"))
        return result
