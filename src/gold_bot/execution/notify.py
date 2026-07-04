"""Notificaciones por Telegram: informe diario y alertas de error.

Para un robot desatendido, el canal de vuelta es tan importante como
las órdenes: si el runner falla una noche y nadie se entera, el
sistema queda cojo en silencio.

Setup (una vez):
  1. En Telegram, habla con @BotFather → /newbot → copia el token.
  2. Envía cualquier mensaje a tu bot recién creado.
  3. python -m gold_bot.execution.notify --discover  → imprime tu
     chat_id; pégalo junto al token en el .env.
  4. python -m gold_bot.execution.notify --test  → mensaje de prueba.
"""

import sys

import requests

from gold_bot.config import settings
from gold_bot.utils.log import get_logger

log = get_logger(__name__)

TIMEOUT = 20


def telegram_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_telegram(text: str) -> bool:
    """Envía un mensaje (HTML). Nunca lanza: un fallo de Telegram no
    debe tumbar al runner — se loguea y punto."""
    if not telegram_configured():
        log.info("telegram_no_configurado")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return True
    except Exception as exc:
        log.error("telegram_fallo", error=str(exc))
        return False


def format_daily_report(result: dict, balance: float, currency: str,
                        regime_label: str, gates_on: int, gates_total: int,
                        brake: float) -> str:
    """Mensaje del informe diario (puro, testeado)."""
    order = result["order_units"]
    order_txt = (f"{'🟢 COMPRA' if order > 0 else '🔴 VENTA'} {abs(order)} oz"
                 if order != 0 else "⚪ sin cambios")
    mode = " (dry-run 🧪)" if result.get("dry_run") else ""
    return (
        f"<b>🥇 gold-bot — informe diario{mode}</b>\n"
        f"Señal del {result['signal_date']}\n\n"
        f"Régimen: <b>{regime_label}</b> · gates {gates_on}/{gates_total}"
        f" · freno ×{brake:.2f}\n"
        f"Exposición objetivo: <b>{result['exposure']:+.1%}</b>"
        f" ({result['target_units']} oz)\n"
        f"Orden: {order_txt}\n"
        f"Balance: <b>{balance:,.2f} {currency}</b>"
    )


def _discover_chat_id() -> None:
    if not settings.telegram_bot_token:
        print("Falta TELEGRAM_BOT_TOKEN en el .env")
        return
    r = requests.get(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
        timeout=TIMEOUT,
    )
    updates = r.json().get("result", [])
    if not updates:
        print("Sin mensajes: envía cualquier cosa a tu bot y reintenta.")
        return
    for u in updates:
        chat = u.get("message", {}).get("chat", {})
        if chat:
            print(f"chat_id: {chat['id']}  ({chat.get('first_name', '')} "
                  f"{chat.get('username', '')})")


if __name__ == "__main__":
    if "--discover" in sys.argv:
        _discover_chat_id()
    elif "--test" in sys.argv:
        ok = send_telegram("🥇 gold-bot: mensaje de prueba — el canal funciona.")
        print("enviado" if ok else "fallo (revisa token/chat_id en .env)")
